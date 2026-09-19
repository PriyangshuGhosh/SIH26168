#include "sih26168/v2x/measurement.hpp"

#include "sih26168/v2x/frames.hpp"
#include "sih26168/v2x/timestamp.hpp"
#include "sih26168/v2x/validation.hpp"

#include <algorithm>
#include <cmath>
#include <vector>

namespace sih26168::v2x {
namespace {

double qualityScale(SourceQuality q, const V2XConfig& cfg) {
    switch (q) {
        case SourceQuality::Low:
            return cfg.quality_low_scale;
        case SourceQuality::High:
            return cfg.quality_high_scale;
        default:
            return cfg.quality_medium_scale;
    }
}

double clampStd(double s, const V2XConfig& cfg) {
    if (!std::isfinite(s) || s <= 0.0) {
        return cfg.max_pos_std_m;
    }
    return std::min(cfg.max_pos_std_m, std::max(cfg.min_pos_std_m, s));
}

bool invert2(const std::array<std::array<double, 2>, 2>& a, std::array<std::array<double, 2>, 2>& inv) {
    const double det = a[0][0] * a[1][1] - a[0][1] * a[1][0];
    if (!std::isfinite(det) || std::abs(det) < 1e-18) {
        return false;
    }
    inv[0][0] = a[1][1] / det;
    inv[0][1] = -a[0][1] / det;
    inv[1][0] = -a[1][0] / det;
    inv[1][1] = a[0][0] / det;
    return true;
}

}  // namespace

double mahalanobis2(double dn, double de, const std::array<std::array<double, 2>, 2>& s_ne) {
    std::array<std::array<double, 2>, 2> inv{};
    if (!invert2(s_ne, inv)) {
        return 1.0e9;
    }
    return dn * (inv[0][0] * dn + inv[0][1] * de) + de * (inv[1][0] * dn + inv[1][1] * de);
}

GateDecision shouldUseMeasurement(const LocalNavigationState& local, const EnuOrigin& origin,
                                  const CooperativeMeasurement& meas, const V2XConfig& cfg,
                                  double& nis, std::string& reason) {
    nis = 0.0;
    if (!meas.has_position || !local.valid || !origin.valid) {
        reason = "unavailable";
        return GateDecision::Unavailable;
    }
    const GeoPosition ego{local.latitude_deg, local.longitude_deg, local.altitude_m};
    const EnuVector p = geoToLocalENU(ego, origin);
    const double dn = meas.north_m - p.north_m;
    const double de = meas.east_m - p.east_m;
    std::array<std::array<double, 2>, 2> S = local.position_cov_ne;
    S[0][0] += meas.position_cov_ne[0][0];
    S[0][1] += meas.position_cov_ne[0][1];
    S[1][0] += meas.position_cov_ne[1][0];
    S[1][1] += meas.position_cov_ne[1][1];
    nis = mahalanobis2(dn, de, S);
    if (!std::isfinite(nis)) {
        reason = "non_finite_nis";
        return GateDecision::Reject;
    }
    if (nis > cfg.nis_reject) {
        reason = "nis_reject";
        return GateDecision::Reject;
    }
    if (nis > cfg.nis_accept) {
        reason = "nis_downweight";
        return GateDecision::Downweight;
    }
    reason = "nis_accept";
    return GateDecision::Accept;
}

void updateRelativeSnapshot(RemoteTrack& track, const LocalNavigationState& local,
                            const EnuOrigin& origin, const V2XConfig& cfg) {
    if (!local.valid || !local.gnss_available || !origin.valid || !track.state.usable) {
        return;
    }
    const GeoPosition ego{local.latitude_deg, local.longitude_deg, local.altitude_m};
    const EnuVector p_ego = geoToLocalENU(ego, origin);
    const EnuVector p_rem = track.state.position_enu;
    double ve = 0.0;
    double vn = 0.0;
    vehicleFrameToNavigationEnu(local.v_x, local.v_y, local.yaw_rad, ve, vn);
    track.relative.time_s = local.timestamp_s;
    track.relative.r_enu = {p_rem.east_m - p_ego.east_m, p_rem.north_m - p_ego.north_m, 0.0};
    track.relative.v_rel_enu = {track.state.velocity_enu.east_m - ve,
                                track.state.velocity_enu.north_m - vn, 0.0};
    const double pnn = local.position_cov_ne[0][0];
    const double pee = local.position_cov_ne[1][1];
    const double remote_var = track.state.pos_std_m * track.state.pos_std_m;
    track.relative.cov_m2 = std::max(1.0, 0.5 * (pnn + pee) + remote_var);
    track.relative.valid = true;
    (void)cfg;
}

CooperativeMeasurement fuseTracks(const std::vector<RemoteTrack>& tracks,
                                  const LocalNavigationState& local, const EnuOrigin& origin,
                                  const V2XConfig& cfg) {
    CooperativeMeasurement meas{};
    meas.timestamp_s = local.timestamp_s;
    meas.source = MessageSource::Simulator;
    if (!local.valid || !origin.valid) {
        meas.kind = CooperativeKind::None;
        return meas;
    }
    if (local.gnss_available) {
        meas.kind = CooperativeKind::None;
        return meas;
    }

    struct Cand {
        double n{0.0};
        double e{0.0};
        double vn{0.0};
        double ve{0.0};
        double var{0.0};
        double age{0.0};
        SourceQuality q{SourceQuality::Unknown};
        CooperativeKind kind{CooperativeKind::RelativeTransferPosition};
    };
    std::vector<Cand> cands;
    double ve_ego = 0.0;
    double vn_ego = 0.0;
    vehicleFrameToNavigationEnu(local.v_x, local.v_y, local.yaw_rad, ve_ego, vn_ego);

    for (const auto& tr : tracks) {
        if (!tr.state.usable) {
            continue;
        }
        Cand c{};
        c.age = tr.state.age_s;
        c.q = tr.state.quality;
        c.vn = tr.state.velocity_enu.north_m;
        c.ve = tr.state.velocity_enu.east_m;
        const double age_s = ageInflationScale(tr.state.age_s, cfg.age_time_constant_s);
        const double spd = speedMagnitude(tr.state.velocity_enu);
        const double tsync = timeSyncPositionStdM(cfg.clock_offset_std_s, spd);
        const double qs = qualityScale(tr.state.quality, cfg);
        double std_m = clampStd(tr.state.pos_std_m * qs * age_s, cfg);

        if (tr.state.has_explicit_relative) {
            c.e = tr.state.position_enu.east_m - tr.state.relative_enu.east_m;
            c.n = tr.state.position_enu.north_m - tr.state.relative_enu.north_m;
            const double rstd =
                clampStd(tr.state.relative_std_m > 0.0 ? tr.state.relative_std_m : std_m, cfg);
            c.var = std_m * std_m + rstd * rstd + tsync * tsync;
            c.kind = CooperativeKind::ExplicitRelative;
            cands.push_back(c);
            continue;
        }
        if (tr.relative.valid &&
            (local.timestamp_s - tr.relative.time_s) <= cfg.relative_snapshot_max_age_s) {
            const double dt = std::max(0.0, local.timestamp_s - tr.relative.time_s);
            const EnuVector r_pred{tr.relative.r_enu.east_m +
                                       (tr.state.velocity_enu.east_m - ve_ego) * dt,
                                   tr.relative.r_enu.north_m +
                                       (tr.state.velocity_enu.north_m - vn_ego) * dt,
                                   0.0};
            const double proc = cfg.max_rel_process_std_mps * dt;
            const double var_r = tr.relative.cov_m2 + proc * proc;
            c.e = tr.state.position_enu.east_m - r_pred.east_m;
            c.n = tr.state.position_enu.north_m - r_pred.north_m;
            c.var = std_m * std_m + var_r + tsync * tsync;
            c.kind = CooperativeKind::RelativeTransferPosition;
            cands.push_back(c);
        }
    }

    if (cands.empty()) {
        meas.kind = CooperativeKind::None;
        return meas;
    }

    if (cands.size() >= 3) {
        std::vector<double> ns;
        ns.reserve(cands.size());
        for (const auto& c : cands) {
            ns.push_back(c.n);
        }
        std::sort(ns.begin(), ns.end());
        const double med = ns[ns.size() / 2];
        std::vector<Cand> kept;
        for (const auto& c : cands) {
            if (std::abs(c.n - med) < 40.0) {
                kept.push_back(c);
            }
        }
        if (!kept.empty()) {
            cands.swap(kept);
        }
    }

    double wsum = 0.0;
    double n = 0.0;
    double e = 0.0;
    double vn = 0.0;
    double ve = 0.0;
    double age = 0.0;
    for (const auto& c : cands) {
        const double w = 1.0 / std::max(c.var, 1e-6);
        wsum += w;
        n += w * c.n;
        e += w * c.e;
        vn += w * c.vn;
        ve += w * c.ve;
        age += w * c.age;
    }
    n /= wsum;
    e /= wsum;
    vn /= wsum;
    ve /= wsum;
    age /= wsum;
    meas.north_m = n;
    meas.east_m = e;
    meas.v_north_mps = vn;
    meas.v_east_mps = ve;
    meas.age_s = age;
    const double fused_var = 1.0 / wsum;
    meas.position_cov_ne[0][0] = fused_var;
    meas.position_cov_ne[1][1] = fused_var;
    meas.position_cov_ne[0][1] = 0.0;
    meas.position_cov_ne[1][0] = 0.0;
    meas.has_position = true;
    meas.has_velocity = true;
    meas.contributing_vehicles = static_cast<int>(cands.size());
    meas.kind = cands.size() > 1 ? CooperativeKind::ClusterConsensus
                                 : CooperativeKind::RelativeTransferPosition;
    meas.quality = cands.front().q;
    return meas;
}

}  // namespace sih26168::v2x
