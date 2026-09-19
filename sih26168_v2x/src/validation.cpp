#include "sih26168/v2x/validation.hpp"

#include "sih26168/v2x/frames.hpp"
#include "sih26168/v2x/timestamp.hpp"

#include <cmath>

namespace sih26168::v2x {

double speedMagnitude(const EnuVector& v) {
    return std::sqrt(v.east_m * v.east_m + v.north_m * v.north_m + v.up_m * v.up_m);
}

double accelMagnitude(const EnuVector& a) {
    return std::sqrt(a.east_m * a.east_m + a.north_m * a.north_m + a.up_m * a.up_m);
}

bool isFiniteMessage(const NormalizedV2XMessage& msg) {
    return finiteNumber(msg.time.sender_time_s) && finiteNumber(msg.time.receive_time_s) &&
           finiteNumber(msg.time.clock_offset_s) && finiteNumber(msg.geo.latitude_deg) &&
           finiteNumber(msg.geo.longitude_deg) && finiteNumber(msg.geo.altitude_m) &&
           finiteNumber(msg.velocity_enu.east_m) && finiteNumber(msg.velocity_enu.north_m) &&
           finiteNumber(msg.velocity_enu.up_m) && finiteNumber(msg.acceleration_enu.east_m) &&
           finiteNumber(msg.acceleration_enu.north_m) && finiteNumber(msg.acceleration_enu.up_m) &&
           finiteNumber(msg.heading_rad) && finiteNumber(msg.yaw_rate_rps) &&
           finiteNumber(msg.declared_pos_std_m) && finiteNumber(msg.declared_vel_std_mps);
}

ValidationResult validateKinematics(const NormalizedV2XMessage& msg, const V2XConfig& cfg,
                                    double last_sender_time_s, const GeoPosition* last_geo) {
    ValidationResult r{};
    if (msg.vehicle_id.empty()) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "empty_id";
        return r;
    }
    if (!isFiniteMessage(msg)) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "non_finite";
        return r;
    }
    if (!validLatitude(msg.geo.latitude_deg) || !validLongitude(msg.geo.longitude_deg)) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "invalid_coordinates";
        return r;
    }
    if (msg.declared_pos_std_m <= 0.0 || msg.declared_vel_std_mps < 0.0) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "invalid_covariance";
        return r;
    }
    const double spd = speedMagnitude(msg.velocity_enu);
    if (spd > cfg.max_speed_mps) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "impossible_speed";
        return r;
    }
    if (accelMagnitude(msg.acceleration_enu) > cfg.max_accel_mps2) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "impossible_accel";
        return r;
    }
    if (std::abs(msg.yaw_rate_rps) > cfg.max_yaw_rate_rps) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "impossible_yaw_rate";
        return r;
    }

    const auto timing = evaluateTiming(msg.time, last_sender_time_s, cfg.max_message_age_s,
                                       cfg.min_dt_s);
    r.age_s = timing.message_age_s;
    r.duplicate = timing.duplicate;
    r.out_of_order = timing.out_of_order;
    if (timing.stale) {
        r.disposition = SecurityStatus::Stale;
        r.reason = "stale_or_future";
        return r;
    }
    if (timing.duplicate) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "duplicate";
        return r;
    }
    if (timing.out_of_order) {
        r.disposition = SecurityStatus::Invalid;
        r.reason = "out_of_order";
        return r;
    }
    if (last_geo != nullptr) {
        EnuOrigin tmp{last_geo->latitude_deg, last_geo->longitude_deg, last_geo->altitude_m, true};
        const EnuVector jump = geoToLocalENU(msg.geo, tmp);
        const double jm = std::sqrt(jump.east_m * jump.east_m + jump.north_m * jump.north_m);
        if (jm > cfg.reject_jump_m) {
            r.disposition = SecurityStatus::Invalid;
            r.reason = "impossible_jump";
            return r;
        }
    }
    r.disposition = SecurityStatus::Validated;
    r.reason = "ok";
    return r;
}

}  // namespace sih26168::v2x
