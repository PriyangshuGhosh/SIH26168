#include "sih26168/v2x/core.hpp"

#include "sih26168/v2x/frames.hpp"
#include "sih26168/v2x/timestamp.hpp"
#include "sih26168/v2x/validation.hpp"

#include <utility>

namespace sih26168::v2x {

V2XCore::V2XCore(V2XConfig config) : config_(config) {
    security_ = makeMockSecurityProvider();
    origin_.latitude_deg = config_.origin_latitude_deg;
    origin_.longitude_deg = config_.origin_longitude_deg;
    origin_.altitude_m = config_.origin_altitude_m;
    origin_.valid = config_.origin_locked;
    health_.transport_name = "none";
}

void V2XCore::reset() {
    tracks_.clear();
    health_ = HealthStatus{};
    health_.transport_name = transport_ ? transport_->name() : "none";
    if (!config_.origin_locked) {
        origin_.valid = false;
    }
}

void V2XCore::setTransport(std::unique_ptr<IV2XTransport> transport) {
    transport_ = std::move(transport);
    health_.transport_name = transport_ ? transport_->name() : "none";
    health_.transport_ok = !transport_ || transport_->ok();
}

void V2XCore::setSecurityProvider(std::unique_ptr<IV2XSecurityProvider> provider) {
    security_ = std::move(provider);
}

void V2XCore::lockOrigin(const EnuOrigin& origin) {
    origin_ = origin;
    origin_.valid = true;
    config_.origin_locked = true;
}

void V2XCore::ingest(const NormalizedV2XMessage& message) {
    ++health_.received;
    std::string sec_reason;
    const SecurityStatus sec =
        security_ ? security_->evaluate(message, config_, sec_reason) : SecurityStatus::Unverified;
    if (sec == SecurityStatus::Rejected || sec == SecurityStatus::Invalid) {
        ++health_.rejected;
        return;
    }
    auto it = tracks_.find(message.vehicle_id);
    const double last_t = (it == tracks_.end()) ? -1.0 : it->second.last_sender_time_s;
    const GeoPosition* last_geo = nullptr;
    GeoPosition last_geo_store{};
    if (it != tracks_.end() && it->second.have_geo) {
        last_geo_store = it->second.last_geo;
        last_geo = &last_geo_store;
    }
    const ValidationResult kin = validateKinematics(message, config_, last_t, last_geo);
    if (kin.duplicate) {
        ++health_.duplicates;
        ++health_.rejected;
        return;
    }
    if (kin.out_of_order) {
        ++health_.out_of_order;
        ++health_.rejected;
        return;
    }
    if (kin.disposition == SecurityStatus::Stale) {
        ++health_.stale;
        ++health_.rejected;
        return;
    }
    if (kin.disposition != SecurityStatus::Validated) {
        ++health_.rejected;
        return;
    }
    ingestValidated(message, kin, sec);
}

void V2XCore::ingestValidated(const NormalizedV2XMessage& message, const ValidationResult& kin,
                              SecurityStatus security) {
    if (static_cast<int>(tracks_.size()) >= config_.max_vehicles &&
        tracks_.find(message.vehicle_id) == tracks_.end()) {
        ++health_.rejected;
        return;
    }
    RemoteTrack& tr = tracks_[message.vehicle_id];
    tr.state.vehicle_id = message.vehicle_id;
    tr.state.timestamp_s = message.time.sender_time_s;
    tr.state.geo = message.geo;
    if (!origin_.valid) {
        origin_.latitude_deg = config_.origin_latitude_deg;
        origin_.longitude_deg = config_.origin_longitude_deg;
        origin_.altitude_m = config_.origin_altitude_m;
        origin_.valid = true;
    }
    tr.state.position_enu = geoToLocalENU(message.geo, origin_);
    tr.state.velocity_enu = message.velocity_enu;
    tr.state.acceleration_enu = message.acceleration_enu;
    tr.state.heading_rad = wrapPi(message.heading_rad);
    tr.state.yaw_rate_rps = message.yaw_rate_rps;
    tr.state.dimensions = message.dimensions;
    tr.state.message_type = message.message_type;
    tr.state.source = message.source;
    tr.state.quality = message.quality;
    tr.state.security = (security == SecurityStatus::Unverified) ? SecurityStatus::Validated : security;
    tr.state.age_s = kin.age_s;
    tr.state.pos_std_m = message.declared_pos_std_m;
    tr.state.vel_std_mps = message.declared_vel_std_mps;
    tr.state.usable = true;
    tr.state.has_explicit_relative = message.has_explicit_relative;
    tr.state.relative_enu = message.relative_enu;
    tr.state.relative_std_m = message.relative_std_m;
    tr.last_sender_time_s = message.time.sender_time_s;
    tr.last_geo = message.geo;
    tr.have_geo = true;
    ++tr.updates;
    ++health_.validated;
    health_.tracked_vehicles = tracks_.size();
}

std::size_t V2XCore::pollTransport(double now_s) {
    if (!transport_) {
        return 0;
    }
    health_.transport_ok = transport_->ok();
    auto msgs = transport_->poll(now_s);
    for (const auto& m : msgs) {
        ingest(m);
    }
    prune(now_s);
    return msgs.size();
}

void V2XCore::prune(double now_s) {
    for (auto it = tracks_.begin(); it != tracks_.end();) {
        if (now_s - it->second.state.timestamp_s > config_.track_timeout_s) {
            it = tracks_.erase(it);
        } else {
            ++it;
        }
    }
    health_.tracked_vehicles = tracks_.size();
}

CooperativeMeasurementResult V2XCore::getCooperativeMeasurement(const LocalNavigationState& local) {
    CooperativeMeasurementResult result{};
    if (local.valid && !origin_.valid) {
        origin_ = EnuOrigin{local.latitude_deg, local.longitude_deg, local.altitude_m, true};
    }
    prune(local.timestamp_s);
    if (local.valid && local.gnss_available) {
        for (auto& kv : tracks_) {
            updateRelativeSnapshot(kv.second, local, origin_, config_);
        }
    }
    std::vector<RemoteTrack> list;
    list.reserve(tracks_.size());
    for (const auto& kv : tracks_) {
        list.push_back(kv.second);
    }
    if (list.empty() || !local.valid) {
        result.decision = GateDecision::Unavailable;
        result.reason = list.empty() ? "no_v2x" : "invalid_local";
        return result;
    }
    result.measurement = fuseTracks(list, local, origin_, config_);
    if (!result.measurement.has_position) {
        result.decision = GateDecision::Unavailable;
        result.reason = local.gnss_available ? "correlated_with_gnss" : "no_observable_relative";
        return result;
    }
    if (result.measurement.age_s > config_.downweight_age_s &&
        result.measurement.age_s <= config_.max_message_age_s) {
        result.measurement.position_cov_ne[0][0] *= config_.downweight_scale;
        result.measurement.position_cov_ne[1][1] *= config_.downweight_scale;
    }
    result.decision = shouldUseMeasurement(local, origin_, result.measurement, config_, result.nis,
                                           result.reason);
    if (result.decision == GateDecision::Downweight) {
        result.measurement.position_cov_ne[0][0] *= config_.downweight_scale;
        result.measurement.position_cov_ne[1][1] *= config_.downweight_scale;
    }
    if (result.decision == GateDecision::Reject) {
        result.measurement.has_position = false;
    }
    return result;
}

std::vector<RemoteVehicleState> V2XCore::remoteVehicles() const {
    std::vector<RemoteVehicleState> out;
    out.reserve(tracks_.size());
    for (const auto& kv : tracks_) {
        out.push_back(kv.second.state);
    }
    return out;
}

}  // namespace sih26168::v2x
