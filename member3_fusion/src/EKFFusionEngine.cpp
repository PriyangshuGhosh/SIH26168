#include "member3/EKFFusionEngine.hpp"

#include <algorithm>
#include <cmath>

namespace sih26168::member3 {

namespace {

constexpr double kEarthRadiusM = 6378137.0;
constexpr double kPi = 3.14159265358979323846;

constexpr double kMinGnssVariance = 0.25;
constexpr double kDefaultPositionVariance = 4.0;
constexpr double kNhcVariance = 0.04;
constexpr double kYawProcessVariance = 1.0e-4;
constexpr double kVelocityProcessVariance = 0.25;
constexpr double kPositionProcessVariance = 0.01;

bool finiteValue(double value) {
    return std::isfinite(value);
}

}  // namespace

EKFFusionEngine::EKFFusionEngine() {
    reset();
}

void EKFFusionEngine::reset() {
    x_.setZero();

    P_.setIdentity();
    initializeCovariance();

    state_ = NavigationState{};

    have_time_ = false;
    last_timestamp_ = 0.0;

    have_reference_ = false;
    reference_latitude_ = 0.0;
    reference_longitude_ = 0.0;
    reference_altitude_ = 0.0;

    have_ai_speed_ = false;
    ai_speed_mps_ = 0.0;
    ai_speed_variance_ = 0.05;

    have_gnss_ = false;
}

void EKFFusionEngine::initializeCovariance() {
    P_.setZero();

    P_(0, 0) = 25.0;
    P_(1, 1) = 25.0;

    P_(2, 2) = 4.0;
    P_(3, 3) = 4.0;

    P_(4, 4) = kPi * kPi;
}

double EKFFusionEngine::normalizeYaw(double yaw) {
    while (yaw > kPi) {
        yaw -= 2.0 * kPi;
    }

    while (yaw < -kPi) {
        yaw += 2.0 * kPi;
    }

    return yaw;
}

bool EKFFusionEngine::validGnss(
    const GnssMeasurement& gnss) const {

    if (!finiteValue(gnss.timestamp) ||
        !finiteValue(gnss.latitude) ||
        !finiteValue(gnss.longitude) ||
        !finiteValue(gnss.altitude) ||
        !finiteValue(gnss.speed_mps) ||
        !finiteValue(gnss.hdop)) {
        return false;
    }

    if (gnss.latitude < -90.0 ||
        gnss.latitude > 90.0) {
        return false;
    }

    if (gnss.longitude < -180.0 ||
        gnss.longitude > 180.0) {
        return false;
    }

    if (gnss.speed_mps < 0.0 ||
        gnss.speed_mps > 100.0) {
        return false;
    }

    if (gnss.hdop <= 0.0 ||
        gnss.hdop > 2.5) {
        return false;
    }

    if (gnss.num_sats < 6) {
        return false;
    }

    return true;
}

void EKFFusionEngine::latLonToLocal(
    double latitude,
    double longitude,
    double& north,
    double& east) const {

    const double lat0 =
        reference_latitude_ * kPi / 180.0;

    const double dlat =
        (latitude - reference_latitude_) *
        kPi / 180.0;

    const double dlon =
        (longitude - reference_longitude_) *
        kPi / 180.0;

    north = dlat * kEarthRadiusM;

    east =
        dlon *
        kEarthRadiusM *
        std::cos(lat0);
}

void EKFFusionEngine::localToLatLon(
    double north,
    double east,
    double& latitude,
    double& longitude) const {

    const double lat0 =
        reference_latitude_ * kPi / 180.0;

    latitude =
        reference_latitude_ +
        (north / kEarthRadiusM) *
        180.0 / kPi;

    const double cosLat =
        std::max(std::cos(lat0), 1.0e-8);

    longitude =
        reference_longitude_ +
        (east / (kEarthRadiusM * cosLat)) *
        180.0 / kPi;
}

void EKFFusionEngine::predict(
    const member2::AlignedIMUFrame& imu,
    NavigationMode mode) {

    state_.mode = mode;

    if (!finiteValue(imu.timestamp) ||
        !finiteValue(imu.ax_v) ||
        !finiteValue(imu.ay_v) ||
        !finiteValue(imu.az_v) ||
        !finiteValue(imu.gz_v)) {
        return;
    }

    if (!have_time_) {
        have_time_ = true;
        last_timestamp_ = imu.timestamp;
        state_.timestamp = imu.timestamp;

        updateNavigationState();
        return;
    }

    double dt =
        imu.timestamp - last_timestamp_;

    if (!finiteValue(dt) || dt <= 0.0) {
        return;
    }

    if (dt > 1.0) {
        last_timestamp_ = imu.timestamp;
        state_.timestamp = imu.timestamp;

        P_(2, 2) += 4.0;
        P_(3, 3) += 4.0;
        P_(4, 4) += 0.5;

        updateNavigationState();
        return;
    }

    dt = std::min(dt, 0.1);

    const double yaw = x_(4);

    // Member 2 outputs specific force in the vehicle frame.
    //
    // Vehicle Z is aligned with gravity-up, so az_v contains
    // approximately +9.80665 m/s^2 while stationary.
    //
    // Horizontal navigation therefore uses ax_v and ay_v directly.
    const double ax = imu.ax_v;
    const double ay = imu.ay_v;
    const double gz = imu.gz_v;

    const double oldVx = x_(2);
    const double oldVy = x_(3);

    x_(2) += ax * dt;
    x_(3) += ay * dt;

    x_(4) =
        normalizeYaw(x_(4) + gz * dt);

    const double c = std::cos(yaw);
    const double s = std::sin(yaw);

    const double vn =
        oldVx * c - oldVy * s;

    const double ve =
        oldVx * s + oldVy * c;

    x_(0) += vn * dt;
    x_(1) += ve * dt;

    Eigen::Matrix<double, kStateDim, kStateDim> F =
        Eigen::Matrix<double, kStateDim, kStateDim>::Identity();

    F(0, 2) = c * dt;
    F(0, 3) = -s * dt;

    F(1, 2) = s * dt;
    F(1, 3) = c * dt;

    F(0, 4) =
        (-oldVx * s - oldVy * c) * dt;

    F(1, 4) =
        (oldVx * c - oldVy * s) * dt;

    Eigen::Matrix<double, kStateDim, kStateDim> Q =
        Eigen::Matrix<double, kStateDim, kStateDim>::Zero();

    Q(0, 0) =
        kPositionProcessVariance * dt;

    Q(1, 1) =
        kPositionProcessVariance * dt;

    Q(2, 2) =
        kVelocityProcessVariance * dt;

    Q(3, 3) =
        kVelocityProcessVariance * dt;

    Q(4, 4) =
        kYawProcessVariance * dt;

    P_ =
        F * P_ * F.transpose() + Q;

    updateNonHolonomicConstraint();

    last_timestamp_ = imu.timestamp;
    state_.timestamp = imu.timestamp;

    updateNavigationState();
}

void EKFFusionEngine::updateNonHolonomicConstraint() {
    const double innovation = -x_(3);

    Eigen::Matrix<double, 1, kStateDim> H =
        Eigen::Matrix<double, 1, kStateDim>::Zero();

    H(0, 3) = 1.0;

    const double S =
        (H * P_ * H.transpose())(0, 0) +
        kNhcVariance;

    if (!finiteValue(S) || S <= 1.0e-12) {
        return;
    }

    const Eigen::Matrix<double, kStateDim, 1> K =
        P_ * H.transpose() / S;

    x_ += K * innovation;

    const Eigen::Matrix<double, kStateDim, kStateDim> I =
        Eigen::Matrix<double, kStateDim, kStateDim>::Identity();

    P_ =
        (I - K * H) * P_;

    x_(4) = normalizeYaw(x_(4));
}

void EKFFusionEngine::updatePositionMeasurement(
    double north,
    double east,
    double variance) {

    Eigen::Matrix<double, 2, kStateDim> H =
        Eigen::Matrix<double, 2, kStateDim>::Zero();

    H(0, 0) = 1.0;
    H(1, 1) = 1.0;

    Eigen::Vector2d z;
    z << north, east;

    const Eigen::Vector2d innovation =
        z - x_.segment<2>(0);

    const double safeVariance =
        std::max(variance, kMinGnssVariance);

    Eigen::Matrix2d R =
        Eigen::Matrix2d::Identity() *
        safeVariance;

    const Eigen::Matrix2d S =
        H * P_ * H.transpose() + R;

    if (!S.allFinite()) {
        return;
    }

    const Eigen::Matrix<double, kStateDim, 2> K =
        P_ * H.transpose() * S.inverse();

    x_ += K * innovation;

    const Eigen::Matrix<double, kStateDim, kStateDim> I =
        Eigen::Matrix<double, kStateDim, kStateDim>::Identity();

    P_ =
        (I - K * H) * P_;

    x_(4) = normalizeYaw(x_(4));
}

void EKFFusionEngine::updateSpeedMeasurement(
    double measuredSpeed,
    double variance) {

    if (!finiteValue(measuredSpeed) ||
        !finiteValue(variance) ||
        measuredSpeed < 0.0 ||
        variance <= 0.0) {
        return;
    }

    const double vx = x_(2);
    const double vy = x_(3);

    const double speed =
        std::sqrt(vx * vx + vy * vy);

    Eigen::Matrix<double, 1, kStateDim> H =
        Eigen::Matrix<double, 1, kStateDim>::Zero();

    if (speed > 1.0e-6) {
        H(0, 2) = vx / speed;
        H(0, 3) = vy / speed;
    } else {
        H(0, 2) = 1.0;
    }

    const double innovation =
        measuredSpeed - speed;

    const double S =
        (H * P_ * H.transpose())(0, 0) +
        std::max(variance, 1.0e-4);

    if (!finiteValue(S) || S <= 1.0e-12) {
        return;
    }

    const Eigen::Matrix<double, kStateDim, 1> K =
        P_ * H.transpose() / S;

    x_ += K * innovation;

    const Eigen::Matrix<double, kStateDim, kStateDim> I =
        Eigen::Matrix<double, kStateDim, kStateDim>::Identity();

    P_ =
        (I - K * H) * P_;

    x_(4) = normalizeYaw(x_(4));
}

void EKFFusionEngine::updateGnss(
    const GnssMeasurement& gnss) {

    if (!validGnss(gnss)) {
        return;
    }

    if (!have_reference_) {
        have_reference_ = true;

        reference_latitude_ =
            gnss.latitude;

        reference_longitude_ =
            gnss.longitude;

        reference_altitude_ =
            gnss.altitude;

        x_(0) = 0.0;
        x_(1) = 0.0;

        if (!have_time_) {
            have_time_ = true;
            last_timestamp_ =
                gnss.timestamp;
        }

        state_.timestamp =
            gnss.timestamp;
    }

    double north = 0.0;
    double east = 0.0;

    latLonToLocal(
        gnss.latitude,
        gnss.longitude,
        north,
        east);

    double positionVariance =
        kDefaultPositionVariance;

    if (gnss.hdop > 0.0 &&
        gnss.hdop < 100.0) {
        positionVariance =
            std::max(
                1.0,
                gnss.hdop * gnss.hdop);
    }

    if (state_.mode ==
        NavigationMode::GNSS_AIDED) {

        updatePositionMeasurement(
            north,
            east,
            positionVariance);

        if (gnss.speed_mps >= 0.0) {
            const double speedVariance =
                std::max(
                    0.25,
                    positionVariance * 0.05);

            updateSpeedMeasurement(
                gnss.speed_mps,
                speedVariance);
        }
    }

    have_gnss_ = true;

    state_.timestamp =
        gnss.timestamp;

    updateNavigationState();
}

void EKFFusionEngine::updateAiSpeed(
    const AiSpeedMeasurement& speed) {

    if (!speed.valid ||
        !finiteValue(speed.timestamp) ||
        !finiteValue(speed.velocity_mps) ||
        !finiteValue(speed.variance_m2s2) ||
        speed.velocity_mps < 0.0 ||
        speed.variance_m2s2 <= 0.0) {
        return;
    }

    have_ai_speed_ = true;

    ai_speed_mps_ =
        speed.velocity_mps;

    ai_speed_variance_ =
        std::max(
            speed.variance_m2s2,
            1.0e-4);

    updateSpeedMeasurement(
        ai_speed_mps_,
        ai_speed_variance_);

    state_.timestamp =
        speed.timestamp;

    updateNavigationState();
}

void EKFFusionEngine::updateNavigationState() {
    state_.v_x = x_(2);
    state_.v_y = x_(3);

    state_.yaw_rad =
        normalizeYaw(x_(4));

    if (have_reference_) {
        localToLatLon(
            x_(0),
            x_(1),
            state_.latitude,
            state_.longitude);

        state_.altitude =
            reference_altitude_;
    }

    state_.position_cov_m2[0][0] =
        std::max(0.0, P_(0, 0));

    state_.position_cov_m2[0][1] =
        P_(0, 1);

    state_.position_cov_m2[1][0] =
        P_(1, 0);

    state_.position_cov_m2[1][1] =
        std::max(0.0, P_(1, 1));
}

}  // namespace sih26168::member3