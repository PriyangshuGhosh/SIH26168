#include "member3/EKFFusionEngine.hpp"

#include <cassert>
#include <cmath>
#include <iostream>

namespace {

using sih26168::member2::AlignedIMUFrame;
using sih26168::member3::AiSpeedMeasurement;
using sih26168::member3::EKFFusionEngine;
using sih26168::member3::GnssMeasurement;
using sih26168::member3::NavigationMode;

AlignedIMUFrame makeImu(
    double timestamp,
    double ax = 0.0,
    double ay = 0.0,
    double gz = 0.0) {

    AlignedIMUFrame imu{};
    imu.timestamp = timestamp;
    imu.ax_v = ax;
    imu.ay_v = ay;
    imu.az_v = 9.80665;
    imu.gz_v = gz;
    return imu;
}

void testReset() {
    EKFFusionEngine engine;

    const auto& state = engine.state();

    assert(state.timestamp == 0.0);
    assert(state.latitude == 0.0);
    assert(state.longitude == 0.0);
    assert(state.v_x == 0.0);
    assert(state.v_y == 0.0);
    assert(state.yaw_rad == 0.0);

    std::cout << "PASS: reset/default state\n";
}

void testFirstPredictOnlyInitializesTime() {
    EKFFusionEngine engine;

    engine.predict(
        makeImu(1.0, 2.0, 0.0, 0.0),
        NavigationMode::DEAD_RECKONING);

    const auto& state = engine.state();

    assert(std::abs(state.timestamp - 1.0) < 1.0e-9);
    assert(std::abs(state.v_x) < 1.0e-9);
    assert(std::abs(state.yaw_rad) < 1.0e-9);

    std::cout << "PASS: first predict initializes timestamp\n";
}

void testAccelerationPrediction() {
    EKFFusionEngine engine;

    engine.predict(
        makeImu(0.0),
        NavigationMode::DEAD_RECKONING);

    engine.predict(
        makeImu(0.1, 1.0, 0.0, 0.0),
        NavigationMode::DEAD_RECKONING);

    const auto& state = engine.state();

    assert(std::abs(state.v_x - 0.1) < 0.05);
    assert(std::abs(state.v_y) < 1.0e-6);

    std::cout << "PASS: acceleration prediction\n";
}

void testYawPrediction() {
    EKFFusionEngine engine;

    engine.predict(
        makeImu(0.0),
        NavigationMode::DEAD_RECKONING);

    engine.predict(
        makeImu(0.1, 0.0, 0.0, 1.0),
        NavigationMode::DEAD_RECKONING);

    const auto& state = engine.state();

    assert(std::abs(state.yaw_rad - 0.1) < 0.05);

    std::cout << "PASS: yaw prediction\n";
}

void testNonHolonomicConstraint() {
    EKFFusionEngine engine;

    engine.predict(
        makeImu(0.0),
        NavigationMode::DEAD_RECKONING);

    engine.predict(
        makeImu(0.1, 0.0, 2.0, 0.0),
        NavigationMode::DEAD_RECKONING);

    const auto& state = engine.state();

    assert(std::abs(state.v_y) < 0.01);

    std::cout << "PASS: non-holonomic constraint\n";
}

void testAiSpeedUpdate() {
    EKFFusionEngine engine;

    engine.predict(
        makeImu(0.0),
        NavigationMode::DEAD_RECKONING);

    AiSpeedMeasurement speed{};
    speed.timestamp = 1.0;
    speed.velocity_mps = 5.0;
    speed.variance_m2s2 = 0.05;
    speed.valid = true;

    engine.updateAiSpeed(speed);

    const auto& state = engine.state();

    assert(std::isfinite(state.v_x));
    assert(std::abs(state.v_x - 5.0) < 1.0);

    std::cout << "PASS: AI speed update\n";
}

void testGnssUpdate() {
    EKFFusionEngine engine;

    GnssMeasurement gnss{};
    gnss.timestamp = 1.0;
    gnss.latitude = 17.3850;
    gnss.longitude = 78.4867;
    gnss.altitude = 500.0;
    gnss.speed_mps = 4.0;
    gnss.hdop = 1.0;
    gnss.num_sats = 10;

    engine.updateGnss(gnss);

    const auto& state = engine.state();

    assert(std::isfinite(state.latitude));
    assert(std::isfinite(state.longitude));
    assert(std::abs(state.latitude - gnss.latitude) < 1.0e-6);
    assert(std::abs(state.longitude - gnss.longitude) < 1.0e-6);

    std::cout << "PASS: GNSS update\n";
}

void testInvalidGnssIgnored() {
    EKFFusionEngine engine;

    GnssMeasurement gnss{};
    gnss.timestamp = 1.0;
    gnss.latitude = 17.3850;
    gnss.longitude = 78.4867;
    gnss.altitude = 500.0;
    gnss.hdop = 99.0;
    gnss.num_sats = 0;

    engine.updateGnss(gnss);

    const auto& state = engine.state();

    assert(state.latitude == 0.0);
    assert(state.longitude == 0.0);

    std::cout << "PASS: invalid GNSS ignored\n";
}

}  // namespace

int main() {
    testReset();
    testFirstPredictOnlyInitializesTime();
    testAccelerationPrediction();
    testYawPrediction();
    testNonHolonomicConstraint();
    testAiSpeedUpdate();
    testGnssUpdate();
    testInvalidGnssIgnored();

    std::cout << "\nAll Member 3 tests passed.\n";
    return 0;
}