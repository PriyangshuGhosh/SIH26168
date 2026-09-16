#include "member5/StubFusionEngine.hpp"

#include <cmath>

namespace sih26168::member5 {
namespace {

constexpr double kDegToRad = 3.14159265358979323846 / 180.0;
constexpr double kRadToDeg = 180.0 / 3.14159265358979323846;
constexpr double kMetersPerDegLat = 111320.0;
constexpr double kBangaloreLat = 12.9716;
constexpr double kBangaloreLon = 77.5946;
constexpr double kDefaultAlt = 920.0;

double metersPerDegLon(double lat_deg) {
    return kMetersPerDegLat * std::cos(lat_deg * kDegToRad);
}

void wrapYaw(double& yaw) {
    while (yaw > 3.14159265358979323846) {
        yaw -= 2.0 * 3.14159265358979323846;
    }
    while (yaw < -3.14159265358979323846) {
        yaw += 2.0 * 3.14159265358979323846;
    }
}

}  // namespace

void StubFusionEngine::reset() {
    state_ = sih26168::member3::NavigationState{};
    state_.latitude = kBangaloreLat;
    state_.longitude = kBangaloreLon;
    state_.altitude = kDefaultAlt;
    state_.position_cov_m2[0][0] = 25.0;
    state_.position_cov_m2[1][1] = 25.0;
    have_time_ = false;
    last_t_ = 0.0;
    have_ai_ = false;
    ai_vx_ = 0.0;
    have_gnss_speed_ = false;
    gnss_vx_ = 0.0;
}

void StubFusionEngine::predict(const sih26168::member2::AlignedIMUFrame& imu,
                               sih26168::member3::NavigationMode mode) {
    state_.timestamp = imu.timestamp;
    state_.mode = mode;

    if (!have_time_) {
        last_t_ = imu.timestamp;
        have_time_ = true;
        return;
    }

    const double dt = imu.timestamp - last_t_;
    last_t_ = imu.timestamp;
    if (!(dt > 1.0e-4) || dt > 0.25) {
        return;
    }

    state_.yaw_rad += imu.gz_v * dt;
    wrapYaw(state_.yaw_rad);

    if (mode == sih26168::member3::NavigationMode::GNSS_AIDED && have_gnss_speed_) {
        state_.v_x = gnss_vx_;
    } else if (have_ai_) {
        state_.v_x = ai_vx_;
    } else {
        state_.v_x += imu.ax_v * dt;
        if (state_.v_x < 0.0) {
            state_.v_x = 0.0;
        }
    }
    state_.v_y = 0.0; /* NHC */

    const double vn = state_.v_x * std::cos(state_.yaw_rad);
    const double ve = state_.v_x * std::sin(state_.yaw_rad);
    const double dlat = (vn * dt) / kMetersPerDegLat;
    const double dlon = (ve * dt) / metersPerDegLon(state_.latitude);
    state_.latitude += dlat;
    state_.longitude += dlon;

    if (mode == sih26168::member3::NavigationMode::DEAD_RECKONING) {
        state_.position_cov_m2[0][0] += 0.05;
        state_.position_cov_m2[1][1] += 0.05;
    }

    (void)kRadToDeg;
}

void StubFusionEngine::updateGnss(double timestamp, double lat, double lon, double alt, double speed) {
    state_.timestamp = timestamp;
    if (std::isfinite(lat) && std::isfinite(lon)) {
        state_.latitude = lat;
        state_.longitude = lon;
    }
    if (std::isfinite(alt)) {
        state_.altitude = alt;
    }
    if (std::isfinite(speed) && speed >= 0.0) {
        state_.v_x = speed;
        have_gnss_speed_ = true;
        gnss_vx_ = speed;
    }
    state_.v_y = 0.0;
    state_.position_cov_m2[0][0] = 0.5;
    state_.position_cov_m2[1][1] = 0.5;
    have_time_ = true;
    last_t_ = timestamp;
}

void StubFusionEngine::updateAiSpeed(double timestamp, double v_x, double variance) {
    (void)timestamp;
    if (!std::isfinite(v_x)) {
        return;
    }
    have_ai_ = true;
    ai_vx_ = std::max(0.0, v_x);
    state_.v_x = ai_vx_;
    if (std::isfinite(variance) && variance > 0.0) {
        /* Inflate speed-related position growth when variance is large. */
        const double extra = std::min(1.0, variance);
        state_.position_cov_m2[0][0] += 0.01 * extra;
        state_.position_cov_m2[1][1] += 0.01 * extra;
    }
}

}  // namespace sih26168::member5
