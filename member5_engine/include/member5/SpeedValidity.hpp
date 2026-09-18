#pragma once

#include <string>

namespace sih26168::member5 {

enum class SpeedRejectReason {
    None = 0,
    NonFinite,
    Negative,
    AboveMax,
    ImpossibleJump,
    VarianceInvalid,
    StationaryConflict,
    TimestampInvalid,
    RecoveredDivergence
};

struct SpeedValidityConfig {
    /* Passenger-road demo bound (~198 km/h). Not a physical law; configurable. */
    double max_vehicle_speed_mps{55.0};
    /* ~1.2 g longitudinal; emergency braking/accel envelope for the demo vehicle. */
    double max_speed_change_mps_per_second{12.0};
    double min_speed_variance_m2s2{0.04};
    double max_speed_variance_m2s2{2500.0};
    double stationary_specific_force_xy_mps2{0.45};
};

const char* speedRejectReasonCString(SpeedRejectReason r);

class SpeedValidityFilter {
public:
    explicit SpeedValidityFilter(SpeedValidityConfig config = {});

    void reset();

    /* Candidate is already in m/s. Returns false to reject; last trusted is unchanged. */
    bool accept(double timestamp_s, double speed_mps, SpeedRejectReason* reason = nullptr);

    bool acceptAiMeasurement(double timestamp_s, double speed_mps, double variance_m2s2,
                             SpeedRejectReason* reason = nullptr);

    double lastTrustedMps() const { return last_speed_mps_; }
    double lastTimestamp() const { return last_t_; }
    bool haveTrusted() const { return have_trusted_; }
    SpeedRejectReason lastReject() const { return last_reject_; }
    const SpeedValidityConfig& config() const { return config_; }

    static bool finiteNonNegative(double speed_mps);
    static bool varianceUsable(double variance_m2s2, const SpeedValidityConfig& cfg);

private:
    SpeedValidityConfig config_{};
    bool have_trusted_{false};
    double last_speed_mps_{0.0};
    double last_t_{0.0};
    SpeedRejectReason last_reject_{SpeedRejectReason::None};
};

}  // namespace sih26168::member5
