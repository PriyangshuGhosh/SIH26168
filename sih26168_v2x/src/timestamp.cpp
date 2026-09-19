#include "sih26168/v2x/timestamp.hpp"

#include <cmath>

namespace sih26168::v2x {

MessageTiming evaluateTiming(const TimestampPair& time, double last_sender_time_s, double max_age_s,
                             double min_dt_s) {
    MessageTiming out{};
    if (!std::isfinite(time.sender_time_s) || !std::isfinite(time.receive_time_s) ||
        !std::isfinite(time.clock_offset_s)) {
        out.stale = true;
        out.message_age_s = max_age_s + 1.0;
        return out;
    }
    out.message_age_s = time.receive_time_s - time.sender_time_s - time.clock_offset_s;
    out.estimated_event_time_s = time.receive_time_s - out.message_age_s;
    if (!std::isfinite(out.message_age_s) || out.message_age_s > max_age_s ||
        out.message_age_s < -0.25) {
        out.stale = true;
    }
    if (last_sender_time_s >= 0.0) {
        const double ds = time.sender_time_s - last_sender_time_s;
        if (std::abs(ds) < min_dt_s) {
            out.duplicate = true;
        } else if (ds < 0.0) {
            out.out_of_order = true;
        }
    }
    return out;
}

double ageInflationScale(double age_s, double time_constant_s) {
    if (!std::isfinite(age_s) || age_s <= 0.0) {
        return 1.0;
    }
    const double tau = std::max(time_constant_s, 1e-6);
    const double r = age_s / tau;
    return std::sqrt(1.0 + r * r);
}

double timeSyncPositionStdM(double clock_offset_std_s, double speed_mps) {
    if (!std::isfinite(clock_offset_std_s) || !std::isfinite(speed_mps)) {
        return 1.0e3;
    }
    return std::abs(clock_offset_std_s) * std::abs(speed_mps);
}

}  // namespace sih26168::v2x
