#include "member5/SpeedValidity.hpp"

#include <cmath>

namespace sih26168::member5 {

const char* speedRejectReasonCString(SpeedRejectReason r) {
    switch (r) {
        case SpeedRejectReason::None:
            return "";
        case SpeedRejectReason::NonFinite:
            return "non_finite";
        case SpeedRejectReason::Negative:
            return "negative";
        case SpeedRejectReason::AboveMax:
            return "above_max_vehicle_speed";
        case SpeedRejectReason::ImpossibleJump:
            return "impossible_jump";
        case SpeedRejectReason::VarianceInvalid:
            return "variance_invalid";
        case SpeedRejectReason::StationaryConflict:
            return "stationary_conflict";
        case SpeedRejectReason::TimestampInvalid:
            return "timestamp_invalid";
        case SpeedRejectReason::RecoveredDivergence:
            return "ekf_velocity_recovered";
        default:
            return "unknown";
    }
}

SpeedValidityFilter::SpeedValidityFilter(SpeedValidityConfig config) : config_(config) {}

void SpeedValidityFilter::reset() {
    have_trusted_ = false;
    last_speed_mps_ = 0.0;
    last_t_ = 0.0;
    last_reject_ = SpeedRejectReason::None;
}

bool SpeedValidityFilter::finiteNonNegative(double speed_mps) {
    return std::isfinite(speed_mps) && speed_mps >= 0.0;
}

bool SpeedValidityFilter::varianceUsable(double variance_m2s2, const SpeedValidityConfig& cfg) {
    return std::isfinite(variance_m2s2) && variance_m2s2 >= cfg.min_speed_variance_m2s2 &&
           variance_m2s2 <= cfg.max_speed_variance_m2s2;
}

bool SpeedValidityFilter::accept(double timestamp_s, double speed_mps, SpeedRejectReason* reason) {
    auto fail = [&](SpeedRejectReason r) {
        last_reject_ = r;
        if (reason) {
            *reason = r;
        }
        return false;
    };

    if (!std::isfinite(timestamp_s)) {
        return fail(SpeedRejectReason::TimestampInvalid);
    }
    if (!std::isfinite(speed_mps)) {
        return fail(SpeedRejectReason::NonFinite);
    }
    if (speed_mps < 0.0) {
        return fail(SpeedRejectReason::Negative);
    }
    if (speed_mps > config_.max_vehicle_speed_mps) {
        return fail(SpeedRejectReason::AboveMax);
    }

    if (have_trusted_) {
        const double dt = timestamp_s - last_t_;
        if (!std::isfinite(dt) || dt < 0.0) {
            return fail(SpeedRejectReason::TimestampInvalid);
        }
        if (dt > 0.0) {
            const double dv = std::abs(speed_mps - last_speed_mps_);
            const double max_dv = config_.max_speed_change_mps_per_second * dt;
            if (dv > max_dv && dv > 1.0) {
                return fail(SpeedRejectReason::ImpossibleJump);
            }
        }
    }

    last_speed_mps_ = speed_mps;
    last_t_ = timestamp_s;
    have_trusted_ = true;
    last_reject_ = SpeedRejectReason::None;
    if (reason) {
        *reason = SpeedRejectReason::None;
    }
    return true;
}

bool SpeedValidityFilter::acceptAiMeasurement(double timestamp_s, double speed_mps,
                                              double variance_m2s2, SpeedRejectReason* reason) {
    if (!varianceUsable(variance_m2s2, config_)) {
        last_reject_ = SpeedRejectReason::VarianceInvalid;
        if (reason) {
            *reason = SpeedRejectReason::VarianceInvalid;
        }
        return false;
    }
    return accept(timestamp_s, speed_mps, reason);
}

}  // namespace sih26168::member5
