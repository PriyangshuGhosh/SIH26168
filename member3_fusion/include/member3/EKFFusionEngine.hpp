#pragma once

#include "member2/calibration_types.h"
#include "member3/fusion_types.h"

#include <Eigen/Dense>

namespace sih26168::member3 {

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
    bool recoverDivergedVelocity();
    static double hypotSpeed(double vx, double vy);
    bool updateScalarMeasurement(double innovation,
                                 const Eigen::Matrix<double, 1, kStateDim>& H,
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
