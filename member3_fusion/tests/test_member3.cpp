#include "member3/EKFFusionEngine.hpp"

#include <Eigen/Eigenvalues>

#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>

namespace {
using namespace sih26168::member2;
using namespace sih26168::member3;

AlignedIMUFrame imu(double t,
                   double ax = 0.0,
                   double ay = 0.0,
                   double gz = 0.0,
                   CalibrationStatus status = CalibrationStatus::FULLY_ALIGNED) {
    AlignedIMUFrame frame{};
    frame.timestamp = t;
    frame.ax_v = ax;
    frame.ay_v = ay;
    frame.az_v = 9.80665;
    frame.gz_v = gz;
    frame.status = status;
    return frame;
}

GnssMeasurement gnss(double t, double lat, double lon, double speed = 0.0) {
    GnssMeasurement g{};
    g.timestamp = t;
    g.latitude = lat;
    g.longitude = lon;
    g.altitude = 100.0;
    g.speed_mps = speed;
    g.hdop = 1.0;
    g.num_sats = 10;
    return g;
}

void eight_state_contract() {
    static_assert(EKFFusionEngine::kStateDim == 8);
    EKFFusionEngine e;
    assert(e.stateVector().size() == 8);
    assert(e.covariance().rows() == 8);
    static_assert(sizeof(NavigationMode) == sizeof(std::int32_t));
}

void imu_propagation() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.predict(imu(0.1, 1.0, 2.0, 3.0), NavigationMode::DEAD_RECKONING);
    assert(e.state().v_x > 0.05);
    assert(std::abs(e.state().yaw_rad - 0.3) < 0.05);
}

void prediction_covers_full_interval() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.predict(imu(0.25, 1.0), NavigationMode::DEAD_RECKONING);
    // A 0.25 s interval must not be silently truncated to 0.10 s.
    assert(std::abs(e.state().v_x - 0.25) < 0.02);
}

void nhc_requires_full_alignment() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.predict(imu(0.1, 0.0, 2.0, 0.0, CalibrationStatus::YAW_UNCERTAIN),
              NavigationMode::DEAD_RECKONING);
    assert(std::abs(e.state().v_y) > 0.05);

    e.predict(imu(0.2), NavigationMode::DEAD_RECKONING);
    assert(std::abs(e.state().v_y) < 0.2);
}

void gnss_update() {
    EKFFusionEngine e;
    e.updateGnss(gnss(0.0, 17.385, 78.4867, 4.0));
    assert(e.state().valid);
    e.predict(imu(0.1), NavigationMode::GNSS_AIDED);
    e.updateGnss(gnss(0.1, 17.3851, 78.4868, 4.0));
    assert(e.state().last_gnss_accepted);
}

void gnss_position_gate() {
    EKFFusionEngine e;
    e.updateGnss(gnss(0.0, 17.385, 78.4867));
    e.predict(imu(0.1), NavigationMode::GNSS_AIDED);
    const auto before = e.state();
    e.updateGnss(gnss(0.1, 17.390, 78.4917));
    const auto after = e.state();
    assert(!after.last_gnss_accepted);
    assert(std::abs(after.latitude - before.latitude) < 1e-5);
    assert(std::abs(after.longitude - before.longitude) < 1e-5);
}

void gnss_speed_is_optional() {
    EKFFusionEngine e;
    e.updateGnss(gnss(0.0, 17.385, 78.4867));
    e.predict(imu(0.1), NavigationMode::GNSS_AIDED);

    auto measurement = gnss(0.1, 17.385, 78.4867);
    measurement.speed_mps = std::numeric_limits<double>::quiet_NaN();
    measurement.speed_valid = false;
    e.updateGnss(measurement);
    assert(e.state().last_gnss_accepted);
}

void ai_speed_and_gate() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.updateAiSpeed({1.0, 5.0, 0.25, true});
    assert(e.state().last_ai_speed_accepted);
    const double velocity = e.state().v_x;

    e.updateAiSpeed({1.0, 80.0, 0.01, true});
    assert(!e.state().last_ai_speed_accepted);
    assert(std::abs(e.state().v_x - velocity) < 1e-9);
}

void delayed_measurements_do_not_rewind_public_time() {
    EKFFusionEngine e;
    e.updateGnss(gnss(0.0, 17.385, 78.4867));
    e.predict(imu(1.0), NavigationMode::GNSS_AIDED);
    const double current = e.state().timestamp;

    auto delayed = gnss(0.5, 17.385, 78.4867);
    e.updateGnss(delayed);
    assert(std::abs(e.state().timestamp - current) < 1e-12);

    AiSpeedMeasurement ai{0.5, 0.0, 1.0, true};
    e.updateAiSpeed(ai);
    assert(std::abs(e.state().timestamp - current) < 1e-12);
}

void invalid_inputs_and_timestamps() {
    EKFFusionEngine e;
    e.predict(imu(1.0), NavigationMode::DEAD_RECKONING);
    const double t = e.state().timestamp;

    e.predict(imu(1.0, 10.0), NavigationMode::DEAD_RECKONING);
    assert(std::abs(e.state().timestamp - t) < 1e-12);
    e.predict(imu(0.5, 10.0), NavigationMode::DEAD_RECKONING);
    assert(std::abs(e.state().timestamp - t) < 1e-12);

    auto invalid = imu(2.0);
    invalid.ax_v = std::numeric_limits<double>::quiet_NaN();
    e.predict(invalid, NavigationMode::DEAD_RECKONING);
    assert(std::isfinite(e.state().v_x));
}

void covariance_remains_psd() {
    EKFFusionEngine e;
    e.updateGnss(gnss(0.0, 17.385, 78.4867));
    e.predict(imu(0.01), NavigationMode::GNSS_AIDED);
    const double initialPositionVariance = e.covariance()(0, 0);

    for (int i = 2; i <= 100; ++i) {
        e.predict(imu(i * 0.01, 0.05), NavigationMode::DEAD_RECKONING);
    }

    const auto P = e.covariance();
    assert(P.allFinite());
    assert(P.isApprox(P.transpose(), 1e-10));
    assert(P(0, 0) > initialPositionVariance);

    Eigen::SelfAdjointEigenSolver<EKFFusionEngine::Covariance> solver(P);
    assert(solver.info() == Eigen::Success);
    assert(solver.eigenvalues().minCoeff() >= -1e-8);
}

void large_gap_is_safe() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.predict(imu(2.0, 1.0), NavigationMode::DEAD_RECKONING);
    assert(std::abs(e.state().timestamp - 2.0) < 1e-12);
    assert(std::isfinite(e.state().v_x));
}

void deterministic_blackout_drift() {
    EKFFusionConfig config;
    config.accel_noise_std_mps2 = 0.05;
    config.gyro_noise_std_rps = 0.01;
    EKFFusionEngine e(config);

    e.predict(imu(0.0), NavigationMode::GNSS_AIDED);
    // Establish a 5 m/s straight-line trajectory before the synthetic blackout.
    e.updateAiSpeed({0.0, 5.0, 0.01, true});
    const double blackoutStartPosition = e.stateVector()(0);

    const double bias = 0.03;
    const double trueVelocity = 5.0;
    const double blackoutSeconds = 20.0;
    const double dt = 0.1;
    for (int i = 1; i <= 200; ++i) {
        e.predict(imu(i * dt, bias), NavigationMode::DEAD_RECKONING);
    }

    const double expectedDisplacement = trueVelocity * blackoutSeconds;
    const double actualDisplacement = e.stateVector()(0) - blackoutStartPosition;
    const double drift = std::abs(actualDisplacement - expectedDisplacement);

    // This is a deterministic sensor-bias regression, not a real-driving accuracy claim.
    assert(std::isfinite(drift));
    assert(drift > 5.0);
    assert(drift < 8.0);
    std::cout << "Synthetic 20 s GNSS-blackout drift: " << drift << " m\n";
}

}  // namespace

int main() {
    eight_state_contract();
    imu_propagation();
    prediction_covers_full_interval();
    nhc_requires_full_alignment();
    gnss_update();
    gnss_position_gate();
    gnss_speed_is_optional();
    ai_speed_and_gate();
    delayed_measurements_do_not_rewind_public_time();
    invalid_inputs_and_timestamps();
    covariance_remains_psd();
    large_gap_is_safe();
    deterministic_blackout_drift();
    std::cout << "All Member 3 completion tests passed.\n";
}
