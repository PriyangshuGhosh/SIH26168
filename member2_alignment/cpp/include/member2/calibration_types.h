#pragma once

#include <array>
#include <cstdint>

namespace sih26168::member2 {

enum class CalibrationStatus : std::int32_t {
    UNINITIALIZED = 0,
    STATIC_DETECTED = 1,
    ROLL_PITCH_VALID = 2,
    YAW_UNCERTAIN = 3,
    FULLY_ALIGNED = 4,
    DEGRADED = 5,
    REINITIALIZING = 6,
    INVALID = 7
};

struct CalibrationConfidence {
    double overall{0.0};
    double gravity{0.0};
    double yaw_observability{0.0};
    double temporal{0.0};
    double sensor_quality{1.0};
};

struct FrameAlignerConfig {
    double gravity_mps2{9.80665};
    double sample_rate_hz{100.0};

    int static_window_samples{50};
    double static_accel_var_max{0.08};
    double static_gyro_norm_max{0.04};
    double static_accel_norm_tol{0.18};
    double static_dir_align_rad{0.10};
    double min_static_duration_s{0.40};

    double gravity_ema_alpha{0.08};
    double gravity_max_tilt_jump_rad{0.25};

    double yaw_min_horiz_accel{0.45};
    double yaw_max_gyro_norm{0.18};
    double yaw_shock_accel_max{16.0};
    double yaw_min_evidence{1.6};
    double yaw_pca_ratio_min{2.2};
    double yaw_turn_gyro_min{0.20};
    double yaw_turn_evidence_min{0.8};
    double yaw_hold_s{8.0};

    double gnss_max_hdop{2.5};
    int gnss_min_sats{6};
    double gnss_max_age_s{0.50};
    double gnss_min_accel{0.35};

    double max_accel_norm{80.0};
    double max_gyro_norm{25.0};
    double max_dt_s{0.050};
    double min_dt_s{1.0e-4};
    double gap_reset_s{1.0};

    double fully_aligned_min_confidence{0.62};
    double yaw_uncertain_confidence_cap{0.55};

    double nominal_dt() const { return 1.0 / sample_rate_hz; }
};

struct OptionalGnssAid {
    double timestamp{0.0};
    double speed_mps{0.0};
    double hdop{99.0};
    int num_sats{0};
    double course_rad{0.0};
    bool course_valid{false};
};

struct AlignedIMUFrame {
    double timestamp{0.0};
    double ax_v{0.0};
    double ay_v{0.0};
    double az_v{0.0};
    double gx_v{0.0};
    double gy_v{0.0};
    double gz_v{0.0};
    std::array<double, 4> q_pv{{1.0, 0.0, 0.0, 0.0}};  // [w, x, y, z]
    CalibrationStatus status{CalibrationStatus::UNINITIALIZED};
    CalibrationConfidence confidence{};
};

}  // namespace sih26168::member2
