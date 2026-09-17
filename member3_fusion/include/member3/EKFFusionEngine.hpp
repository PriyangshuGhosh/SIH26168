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

    double position_cov_m2[2][2]{
        {0.5, 0.0},
        {0.0, 0.5}
    };

    NavigationMode mode{
        NavigationMode::DEAD_RECKONING
    };
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

class EKFFusionEngine {
public:
    EKFFusionEngine();

    void reset();

    void predict(
        const member2::AlignedIMUFrame& imu,
        NavigationMode mode);

    void updateGnss(
        const GnssMeasurement& gnss);

    void updateAiSpeed(
        const AiSpeedMeasurement& speed);

    const NavigationState& state() const {
        return state_;
    }

private:
    static constexpr int kStateDim = 5;

    // [north_position,
    //  east_position,
    //  forward_velocity,
    //  lateral_velocity,
    //  yaw]
    Eigen::Matrix<double, kStateDim, 1> x_{
        Eigen::Matrix<double, kStateDim, 1>::Zero()
    };

    Eigen::Matrix<double, kStateDim, kStateDim> P_{
        Eigen::Matrix<double, kStateDim, kStateDim>::Identity()
    };

    NavigationState state_{};

    bool have_time_{false};
    double last_timestamp_{0.0};

    bool have_reference_{false};
    double reference_latitude_{0.0};
    double reference_longitude_{0.0};
    double reference_altitude_{0.0};

    bool have_ai_speed_{false};
    double ai_speed_mps_{0.0};
    double ai_speed_variance_{0.05};

    bool have_gnss_{false};

    void initializeCovariance();

    void updateNavigationState();

    void updatePositionMeasurement(
        double north,
        double east,
        double variance);

    void updateSpeedMeasurement(
        double measuredSpeed,
        double variance);

    void updateNonHolonomicConstraint();

    bool validGnss(
        const GnssMeasurement& gnss) const;

    static double normalizeYaw(double yaw);

    void latLonToLocal(
        double latitude,
        double longitude,
        double& north,
        double& east) const;

    void localToLatLon(
        double north,
        double east,
        double& latitude,
        double& longitude) const;
};

}  // namespace sih26168::member3