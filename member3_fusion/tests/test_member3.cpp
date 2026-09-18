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

void numerical_jacobian_matches_prediction_covariance() {
    EKFFusionConfig config;
    config.accel_noise_std_mps2 = 0.0;
    config.gyro_noise_std_rps = 0.0;
    config.accel_bias_rw_std_mps2_sqrt_s = 0.0;
    config.gyro_bias_rw_std_rps_sqrt_s = 0.0;
    EKFFusionEngine e(config);

    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.updateAiSpeed({0.0, 5.0, 0.25, true});
    e.predict(imu(0.1, 0.4, -0.2, 0.8, CalibrationStatus::YAW_UNCERTAIN),
              NavigationMode::DEAD_RECKONING);

    const auto x0 = e.stateVector();
    const auto P0 = e.covariance();
    const double dt = 0.1;
    const double ax = 0.7;
    const double ay = -0.3;
    const double gz = 0.5;

    auto transition = [&](const EKFFusionEngine::StateVector& x) {
        EKFFusionEngine::StateVector y = x;
        const double yaw = x(4);
        const double c = std::cos(yaw);
        const double s = std::sin(yaw);
        y(0) += (x(2) * c - x(3) * s) * dt;
        y(1) += (x(2) * s + x(3) * c) * dt;
        y(2) += (ax - x(5)) * dt;
        y(3) += (ay - x(6)) * dt;
        y(4) += (gz - x(7)) * dt;
        return y;
    };

    constexpr double eps = 1.0e-6;
    EKFFusionEngine::Covariance Fnum = EKFFusionEngine::Covariance::Zero();
    for (int i = 0; i < EKFFusionEngine::kStateDim; ++i) {
        auto plus = x0;
        auto minus = x0;
        plus(i) += eps;
        minus(i) -= eps;
        Fnum.col(i) = (transition(plus) - transition(minus)) / (2.0 * eps);
    }

    EKFFusionEngine::Covariance F = EKFFusionEngine::Covariance::Identity();
    const double yaw = x0(4);
    const double c = std::cos(yaw);
    const double s = std::sin(yaw);
    F(0, 2) = c * dt;
    F(0, 3) = -s * dt;
    F(1, 2) = s * dt;
    F(1, 3) = c * dt;
    F(0, 4) = (-x0(2) * s - x0(3) * c) * dt;
    F(1, 4) = (x0(2) * c - x0(3) * s) * dt;
    F(2, 5) = -dt;
    F(3, 6) = -dt;
    F(4, 7) = -dt;

    assert((F - Fnum).cwiseAbs().maxCoeff() < 1.0e-7);

    e.predict(imu(0.2, ax, ay, gz, CalibrationStatus::YAW_UNCERTAIN),
              NavigationMode::DEAD_RECKONING);
    const auto expectedP = F * P0 * F.transpose();
    assert((e.covariance() - expectedP).cwiseAbs().maxCoeff() < 1.0e-7);
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
    auto measurement = gnss(0.1, 17.390, 78.4917);
    measurement.speed_valid = false;
    e.updateGnss(measurement);
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

void gnss_speed_survives_position_rejection() {
    EKFFusionEngine e;
    e.updateGnss(gnss(0.0, 17.385, 78.4867));
    e.predict(imu(0.1), NavigationMode::GNSS_AIDED);
    const double before = e.state().v_x;

    auto measurement = gnss(0.1, 17.390, 78.4917, 4.0);
    e.updateGnss(measurement);

    assert(e.state().last_gnss_accepted);
    assert(e.state().v_x > before);
    assert(e.state().v_x < 4.0);
}

void ai_speed_and_gate() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.updateAiSpeed({0.0, 4.0, 0.25, true});
    assert(e.state().last_ai_speed_accepted);
    const double velocity = e.state().v_x;

    e.updateAiSpeed({0.0, 80.0, 0.01, true});
    assert(!e.state().last_ai_speed_accepted);
    assert(std::abs(e.state().v_x - velocity) < 1e-9);
}

void ai_speed_194_mps_vs_nav_2_mps_is_rejected() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.updateAiSpeed({0.0, 2.0, 0.25, true});
    assert(e.state().last_ai_speed_accepted);
    const double before = e.state().v_x;
    assert(std::abs(before - 2.0) < 0.5);

    e.updateAiSpeed({0.0, 194.4, 0.05, true}); /* ~700 km/h */
    assert(!e.state().last_ai_speed_accepted);
    assert(std::abs(e.state().v_x - before) < 1e-9);
    assert(std::hypot(e.state().v_x, e.state().v_y) < 10.0);

    e.updateAiSpeed({0.0, 40.0, 0.05, true}); /* below max, NIS must still reject */
    assert(!e.state().last_ai_speed_accepted);
    assert(std::abs(e.state().v_x - before) < 1e-9);
}

void tiny_variance_is_floored_not_blindly_trusted() {
    EKFFusionEngine e;
    e.predict(imu(0.0), NavigationMode::DEAD_RECKONING);
    e.updateAiSpeed({0.0, 2.0, 0.25, true});
    const double before = e.state().v_x;
    e.updateAiSpeed({0.0, 30.0, 1e-18, true});
    /* Either rejected by NIS or accepted only with floored variance — never a 30 m/s jump. */
    assert(std::abs(e.state().v_x - before) < 5.0);
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
    // Establish a gate-compliant baseline velocity before the synthetic blackout.
    e.updateAiSpeed({0.0, 4.0, 0.25, true});
    const double blackoutStartPosition = e.stateVector()(0);
    const double trueVelocity = e.state().v_x;

    const double bias = 0.03;
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
    numerical_jacobian_matches_prediction_covariance();
    nhc_requires_full_alignment();
    gnss_update();
    gnss_position_gate();
    gnss_speed_is_optional();
    gnss_speed_survives_position_rejection();
    ai_speed_and_gate();
    ai_speed_194_mps_vs_nav_2_mps_is_rejected();
    tiny_variance_is_floored_not_blindly_trusted();
    delayed_measurements_do_not_rewind_public_time();
    invalid_inputs_and_timestamps();
    covariance_remains_psd();
    large_gap_is_safe();
    deterministic_blackout_drift();
    std::cout << "All Member 3 completion tests passed.\n";
}
