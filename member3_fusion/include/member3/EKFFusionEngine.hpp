#pragma once

#include "member2/calibration_types.h"

#include <Eigen/Dense>
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
};

struct GnssMeasurement {
    double timestamp{0.0};
    double latitude{0.0};
    double longitude{0.0};
    double altitude{0.0};
    double speed_mps{0.0};
    double hdop{99.0};
    int num_sats{0};
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
    double gnss_speed_variance_floor_m2s2{0.25};
    double gnss_nis_threshold{5.991};
    double speed_nis_threshold{3.841};
    double nhc_variance_m2s2{0.04};
    double nhc_nis_threshold{3.841};
    double max_measurement_age_s{2.0};
    double max_measurement_lead_s{0.10};
    double max_prediction_dt_s{0.10};
    double max_gap_s{1.0};
    double accel_noise_std_mps2{0.5};
    double gyro_noise_std_rps{0.05};
    double accel_bias_rw_std_mps2_sqrt_s{0.02};
    double gyro_bias_rw_std_rps_sqrt_s{0.002};
    double degraded_process_scale{4.0};
};

class EKFFusionEngine {
public:
    static constexpr int kStateDim = 8;
    using StateVector = Eigen::Matrix<double, kStateDim, 1>;
    using Covariance = Eigen::Matrix<double, kStateDim, kStateDim>;

    explicit EKFFusionEngine(const EKFFusionConfig& config = EKFFusionConfig{});

    void reset();
    void predict(const member2::AlignedIMUFrame& imu, NavigationMode mode);
    void updateGnss(const GnssMeasurement& gnss);
    void updateAiSpeed(const AiSpeedMeasurement& speed);

    const NavigationState& state() const { return state_; }
    const StateVector& stateVector() const { return x_; }
    const Covariance& covariance() const { return P_; }
    const EKFFusionConfig& config() const { return config_; }

private:
    EKFFusionConfig config_{};
    StateVector x_{StateVector::Zero()};
    Covariance P_{Covariance::Identity()};
    NavigationState state_{};

    bool have_time_{false};
    double last_timestamp_{0.0};
    bool have_reference_{false};
    double reference_latitude_{0.0};
    double reference_longitude_{0.0};
    double reference_altitude_{0.0};

    void initializeCovariance();
    void updateNavigationState();
    bool updateSpeedMeasurement(double measuredSpeed, double variance);
    bool updateScalarMeasurement(double innovation,
                                 const Eigen::Matrix<double,1,kStateDim>& H,
                                 double variance, double nisThreshold);
    bool updatePositionMeasurementGated(double north, double east, double variance);
    bool updateNonHolonomicConstraint(const member2::AlignedIMUFrame& imu);

    bool validGnss(const GnssMeasurement& gnss) const;
    bool validMeasurementTime(double timestamp) const;
    static double normalizeYaw(double yaw);
    static bool finiteVector(const StateVector& x);
    static bool finiteCovariance(const Covariance& P);
    static void symmetrize(Covariance& P);
    static void stabilizeCovariance(Covariance& P);

    void latLonToLocal(double latitude, double longitude, double& north, double& east) const;
    void localToLatLon(double north, double east, double& latitude, double& longitude) const;
};

}  // namespace sih26168::member3
