#pragma once

#include <cstdint>

namespace sih26168::member3 {

enum class NavigationMode : std::int32_t {
    GNSS_AIDED = 0,
    DEAD_RECKONING = 1
};

struct NavigationState {
    double timestamp{0.0};
    double latitude{0.0};
    double longitude{0.0};
    double altitude{0.0};
    double v_x{0.0};
    double v_y{0.0};
    double yaw_rad{0.0};
    double position_cov_m2[2][2]{{25.0, 0.0}, {0.0, 25.0}};
    NavigationMode mode{NavigationMode::DEAD_RECKONING};
    bool valid{false};
    bool last_gnss_accepted{false};
    bool last_ai_speed_accepted{false};
    bool last_velocity_recovered{false};
};

struct GnssMeasurement {
    double timestamp{0.0};
    double latitude{0.0};
    double longitude{0.0};
    double altitude{0.0};
    double speed_mps{0.0};
    double hdop{99.0};
    int num_sats{0};
    // Set false when the receiver did not provide a usable GNSS speed.
    bool speed_valid{true};
};

struct AiSpeedMeasurement {
    double timestamp{0.0};
    double velocity_mps{0.0};
    double variance_m2s2{0.05};
    bool valid{false};
};

struct EKFFusionConfig {
    double gnss_max_hdop{2.5};
    int gnss_min_sats{6};
    double gnss_position_sigma_floor_m{1.0};
    // Converts dimensionless HDOP into an estimated horizontal 1-sigma error in metres.
    double gnss_hdop_to_sigma_m{5.0};
    double gnss_speed_variance_floor_m2s2{0.25};
    double gnss_nis_threshold{5.991};
    double speed_nis_threshold{3.841};
    /* Passenger-road demo envelope (~198 km/h). Configurable; not a physics law. */
    double max_vehicle_speed_mps{55.0};
    double min_speed_variance_m2s2{0.04};
    double max_speed_variance_m2s2{2500.0};
    double nhc_variance_m2s2{0.04};
    double nhc_nis_threshold{3.841};
    // Measurements are expected to be timestamp-aligned to the latest EKF epoch.
    // The engine has no IMU history for out-of-sequence replay.
    double max_measurement_age_s{0.10};
    double max_measurement_lead_s{0.0};
    double max_prediction_dt_s{0.10};
    double max_gap_s{1.0};
    double accel_noise_std_mps2{0.5};
    double gyro_noise_std_rps{0.05};
    double accel_bias_rw_std_mps2_sqrt_s{0.02};
    double gyro_bias_rw_std_rps_sqrt_s{0.002};
    double degraded_process_scale{4.0};
};

}  // namespace sih26168::member3
