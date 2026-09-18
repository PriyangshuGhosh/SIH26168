#include "member3/EKFFusionEngine.hpp"

#include <Eigen/Eigenvalues>

#include <algorithm>
#include <cmath>

namespace sih26168::member3 {
namespace {
constexpr double kEarthRadiusM = 6378137.0;
constexpr double kPi = 3.14159265358979323846;
constexpr double kInitialPositionVariance = 25.0;
constexpr double kInitialVelocityVariance = 4.0;
constexpr double kInitialBiasVariance = 0.25;
constexpr double kInitialYawVariance = kPi * kPi;
constexpr double kMinVariance = 1.0e-9;
constexpr double kPsdTolerance = 1.0e-10;
constexpr double kMaxReasonableState = 1.0e9;

bool finiteValue(double v) { return std::isfinite(v); }
}  // namespace

EKFFusionEngine::EKFFusionEngine(const EKFFusionConfig& config) : config_(config) {
    reset();
}

void EKFFusionEngine::reset() {
    x_.setZero();
    initializeCovariance();
    state_ = NavigationState{};
    have_time_ = false;
    last_timestamp_ = 0.0;
    have_reference_ = false;
    reference_latitude_ = 0.0;
    reference_longitude_ = 0.0;
    reference_altitude_ = 0.0;
}

void EKFFusionEngine::initializeCovariance() {
    P_.setZero();
    P_(0, 0) = P_(1, 1) = kInitialPositionVariance;
    P_(2, 2) = P_(3, 3) = kInitialVelocityVariance;
    P_(4, 4) = kInitialYawVariance;
    P_(5, 5) = P_(6, 6) = P_(7, 7) = kInitialBiasVariance;
}

double EKFFusionEngine::normalizeYaw(double yaw) {
    if (!finiteValue(yaw)) return 0.0;
    yaw = std::fmod(yaw + kPi, 2.0 * kPi);
    if (yaw < 0.0) yaw += 2.0 * kPi;
    return yaw - kPi;
}

bool EKFFusionEngine::finiteVector(const StateVector& x) { return x.allFinite(); }
bool EKFFusionEngine::finiteCovariance(const Covariance& P) { return P.allFinite(); }

void EKFFusionEngine::symmetrize(Covariance& P) {
    P = 0.5 * (P + P.transpose());
}

void EKFFusionEngine::stabilizeCovariance(Covariance& P) {
    symmetrize(P);
    if (!P.allFinite()) return;

    Eigen::SelfAdjointEigenSolver<Covariance> solver(P, Eigen::EigenvaluesOnly);
    if (solver.info() == Eigen::Success && solver.eigenvalues().minCoeff() < -kPsdTolerance) {
        Eigen::SelfAdjointEigenSolver<Covariance> fullSolver(P);
        if (fullSolver.info() == Eigen::Success) {
            auto values = fullSolver.eigenvalues();
            for (int i = 0; i < kStateDim; ++i) {
                values(i) = std::max(values(i), kMinVariance);
            }
            P = fullSolver.eigenvectors() * values.asDiagonal() * fullSolver.eigenvectors().transpose();
            symmetrize(P);
        }
    }

    for (int i = 0; i < kStateDim; ++i) {
        if (!finiteValue(P(i, i)) || P(i, i) < kMinVariance) P(i, i) = kMinVariance;
    }
    symmetrize(P);
}

bool EKFFusionEngine::validMeasurementTime(double timestamp) const {
    if (!finiteValue(timestamp)) return false;
    if (!have_time_) return true;
    // The engine does not retain an IMU history, so applying an old measurement
    // at the current state would be mathematically inconsistent. Measurements
    // must therefore be time-aligned to the current filter epoch.
    return timestamp <= last_timestamp_ + config_.max_measurement_lead_s &&
           timestamp >= last_timestamp_ - config_.max_measurement_age_s;
}

bool EKFFusionEngine::validGnss(const GnssMeasurement& g) const {
    const bool validSpeed = !g.speed_valid ||
                            (finiteValue(g.speed_mps) && g.speed_mps >= 0.0 &&
                             g.speed_mps <= config_.max_vehicle_speed_mps);
    return finiteValue(g.timestamp) && finiteValue(g.latitude) && finiteValue(g.longitude) &&
           finiteValue(g.altitude) && finiteValue(g.hdop) && validSpeed &&
           g.latitude >= -90.0 && g.latitude <= 90.0 &&
           g.longitude >= -180.0 && g.longitude <= 180.0 && g.hdop > 0.0 &&
           g.hdop <= config_.gnss_max_hdop && g.num_sats >= config_.gnss_min_sats &&
           validMeasurementTime(g.timestamp);
}

void EKFFusionEngine::latLonToLocal(double lat, double lon, double& north, double& east) const {
    const double lat0 = reference_latitude_ * kPi / 180.0;
    north = (lat - reference_latitude_) * kPi / 180.0 * kEarthRadiusM;
    east = (lon - reference_longitude_) * kPi / 180.0 * kEarthRadiusM * std::cos(lat0);
}

void EKFFusionEngine::localToLatLon(double north, double east, double& lat, double& lon) const {
    const double lat0 = reference_latitude_ * kPi / 180.0;
    lat = reference_latitude_ + north / kEarthRadiusM * 180.0 / kPi;
    lon = reference_longitude_ +
          east / (kEarthRadiusM * std::max(std::abs(std::cos(lat0)), 1e-8)) * 180.0 / kPi;
}

void EKFFusionEngine::predict(const member2::AlignedIMUFrame& imu, NavigationMode mode) {
    state_.mode = mode;
    state_.last_gnss_accepted = false;
    state_.last_ai_speed_accepted = false;
    state_.last_velocity_recovered = false;

    if (!finiteValue(imu.timestamp) || !finiteValue(imu.ax_v) || !finiteValue(imu.ay_v) ||
        !finiteValue(imu.az_v) || !finiteValue(imu.gz_v) ||
        imu.status == member2::CalibrationStatus::INVALID) {
        return;
    }

    if (!have_time_) {
        have_time_ = true;
        last_timestamp_ = imu.timestamp;
        state_.timestamp = imu.timestamp;
        updateNavigationState();
        return;
    }

    const double rawDt = imu.timestamp - last_timestamp_;
    if (!finiteValue(rawDt) || rawDt <= 0.0) return;

    if (rawDt > config_.max_gap_s) {
        last_timestamp_ = imu.timestamp;
        state_.timestamp = imu.timestamp;
        const double gap = std::max(rawDt, 1.0);
        const double aq = config_.accel_noise_std_mps2 * config_.accel_noise_std_mps2;
        const double gq = config_.gyro_noise_std_rps * config_.gyro_noise_std_rps;
        P_(0, 0) += aq * gap * gap * gap / 3.0;
        P_(1, 1) += aq * gap * gap * gap / 3.0;
        P_(2, 2) += aq * gap;
        P_(3, 3) += aq * gap;
        P_(4, 4) += gq * gap;
        stabilizeCovariance(P_);
        updateNavigationState();
        return;
    }

    double remaining = rawDt;
    while (remaining > 0.0) {
        const double dt = std::min(remaining, config_.max_prediction_dt_s);
        const double yaw = x_(4);
        const double c = std::cos(yaw);
        const double s = std::sin(yaw);
        const double oldVx = x_(2);
        const double oldVy = x_(3);
        const double ax = imu.ax_v - x_(5);
        const double ay = imu.ay_v - x_(6);
        const double gz = imu.gz_v - x_(7);

        x_(0) += (oldVx * c - oldVy * s) * dt;
        x_(1) += (oldVx * s + oldVy * c) * dt;
        x_(2) += ax * dt;
        x_(3) += ay * dt;
        x_(4) = normalizeYaw(yaw + gz * dt);

        Eigen::Matrix<double, kStateDim, kStateDim> F =
            Eigen::Matrix<double, kStateDim, kStateDim>::Identity();
        F(0, 2) = c * dt;
        F(0, 3) = -s * dt;
        F(1, 2) = s * dt;
        F(1, 3) = c * dt;
        F(0, 4) = (-oldVx * s - oldVy * c) * dt;
        F(1, 4) = (oldVx * c - oldVy * s) * dt;
        F(2, 5) = -dt;
        F(3, 6) = -dt;
        F(4, 7) = -dt;

        Eigen::Matrix<double, kStateDim, kStateDim> Q =
            Eigen::Matrix<double, kStateDim, kStateDim>::Zero();
        const double scale = (imu.status == member2::CalibrationStatus::FULLY_ALIGNED)
                                 ? 1.0
                                 : config_.degraded_process_scale;
        const double aq = scale * config_.accel_noise_std_mps2 * config_.accel_noise_std_mps2;
        const double gq = scale * config_.gyro_noise_std_rps * config_.gyro_noise_std_rps;
        // Continuous white-acceleration discretization: position-position,
        // position-velocity, and velocity-velocity terms are retained.
        const double dt2 = dt * dt;
        const double dt3 = dt2 * dt;
        Q(0, 0) = Q(1, 1) = aq * dt3 / 3.0;
        Q(0, 2) = Q(2, 0) = aq * dt2 / 2.0;
        Q(1, 3) = Q(3, 1) = aq * dt2 / 2.0;
        Q(2, 2) = Q(3, 3) = aq * dt;
        Q(4, 4) = gq * dt;
        Q(5, 5) =
            config_.accel_bias_rw_std_mps2_sqrt_s * config_.accel_bias_rw_std_mps2_sqrt_s * dt;
        Q(6, 6) = Q(5, 5);
        Q(7, 7) =
            config_.gyro_bias_rw_std_rps_sqrt_s * config_.gyro_bias_rw_std_rps_sqrt_s * dt;

        P_ = F * P_ * F.transpose() + Q;
        stabilizeCovariance(P_);
        remaining -= dt;
    }

    if (imu.status == member2::CalibrationStatus::FULLY_ALIGNED) {
        updateNonHolonomicConstraint(imu);
    }
    if (!finiteVector(x_) || !finiteCovariance(P_)) {
        reset();
        return;
    }
    recoverDivergedVelocity();
    last_timestamp_ = imu.timestamp;
    state_.timestamp = imu.timestamp;
    updateNavigationState();
}

double EKFFusionEngine::hypotSpeed(double vx, double vy) {
    return std::sqrt(vx * vx + vy * vy);
}

bool EKFFusionEngine::recoverDivergedVelocity() {
    const double spd = hypotSpeed(x_(2), x_(3));
    if (!finiteValue(spd) || spd > config_.max_vehicle_speed_mps) {
        x_(2) = 0.0;
        x_(3) = 0.0;
        P_(2, 2) = std::max(P_(2, 2), 25.0);
        P_(3, 3) = std::max(P_(3, 3), 25.0);
        stabilizeCovariance(P_);
        state_.last_velocity_recovered = true;
        return true;
    }
    return false;
}

bool EKFFusionEngine::updateScalarMeasurement(
    double innovation,
    const Eigen::Matrix<double, 1, kStateDim>& H,
    double variance,
    double threshold) {
    if (!finiteValue(innovation) || !finiteValue(variance) || variance <= 0.0 || !H.allFinite()) {
        return false;
    }
    const double S = (H * P_ * H.transpose())(0, 0) + variance;
    if (!finiteValue(S) || S <= kMinVariance) return false;
    const double nis = innovation * innovation / S;
    if (!finiteValue(nis) || nis > threshold) return false;

    const Eigen::Matrix<double, kStateDim, 1> K = P_ * H.transpose() / S;
    const Covariance I = Covariance::Identity();
    const Covariance A = I - K * H;
    x_ += K * innovation;
    P_ = A * P_ * A.transpose() + K * variance * K.transpose();
    stabilizeCovariance(P_);
    x_(4) = normalizeYaw(x_(4));
    return finiteVector(x_) && finiteCovariance(P_);
}

bool EKFFusionEngine::updatePositionMeasurementGated(double north, double east, double variance) {
    Eigen::Matrix<double, 2, kStateDim> H = Eigen::Matrix<double, 2, kStateDim>::Zero();
    H(0, 0) = H(1, 1) = 1.0;
    Eigen::Vector2d innovation;
    innovation << north - x_(0), east - x_(1);
    const double safe = std::max(variance,
                                 config_.gnss_position_sigma_floor_m *
                                     config_.gnss_position_sigma_floor_m);
    const Eigen::Matrix2d R = Eigen::Matrix2d::Identity() * safe;
    const Eigen::Matrix2d S = H * P_ * H.transpose() + R;
    if (!S.allFinite()) return false;

    Eigen::LDLT<Eigen::Matrix2d> ldlt(S);
    if (ldlt.info() != Eigen::Success) return false;
    const Eigen::Vector2d solved = ldlt.solve(innovation);
    if (!solved.allFinite()) return false;
    const double nis = innovation.dot(solved);
    if (!finiteValue(nis) || nis > config_.gnss_nis_threshold) return false;

    const Eigen::Matrix<double, kStateDim, 2> K =
        P_ * H.transpose() * ldlt.solve(Eigen::Matrix2d::Identity());
    const Covariance I = Covariance::Identity();
    const Covariance A = I - K * H;
    x_ += K * innovation;
    P_ = A * P_ * A.transpose() + K * R * K.transpose();
    stabilizeCovariance(P_);
    x_(4) = normalizeYaw(x_(4));
    return finiteVector(x_) && finiteCovariance(P_);
}

bool EKFFusionEngine::updateSpeedMeasurement(double measured, double variance) {
    if (!finiteValue(measured) || !finiteValue(variance) || measured < 0.0 ||
        measured > config_.max_vehicle_speed_mps || variance <= 0.0) {
        return false;
    }
    const double var = std::min(std::max(variance, config_.min_speed_variance_m2s2),
                                config_.max_speed_variance_m2s2);
    Eigen::Matrix<double, 1, kStateDim> H = Eigen::Matrix<double, 1, kStateDim>::Zero();
    H(0, 2) = 1.0;
    return updateScalarMeasurement(measured - x_(2), H, var, config_.speed_nis_threshold);
}

bool EKFFusionEngine::updateNonHolonomicConstraint(const member2::AlignedIMUFrame& imu) {
    if (imu.status != member2::CalibrationStatus::FULLY_ALIGNED) return false;
    Eigen::Matrix<double, 1, kStateDim> H = Eigen::Matrix<double, 1, kStateDim>::Zero();
    H(0, 3) = 1.0;
    return updateScalarMeasurement(-x_(3), H, std::max(config_.nhc_variance_m2s2, 1e-6),
                                   config_.nhc_nis_threshold);
}

void EKFFusionEngine::updateGnss(const GnssMeasurement& g) {
    state_.last_gnss_accepted = false;
    if (!validGnss(g)) return;

    if (!have_reference_) {
        have_reference_ = true;
        reference_latitude_ = g.latitude;
        reference_longitude_ = g.longitude;
        reference_altitude_ = g.altitude;
        x_(0) = x_(1) = 0.0;
        if (!have_time_) {
            have_time_ = true;
            last_timestamp_ = g.timestamp;
            state_.timestamp = g.timestamp;
        }
        state_.last_gnss_accepted = true;
        updateNavigationState();
        return;
    }

    double north = 0.0;
    double east = 0.0;
    latLonToLocal(g.latitude, g.longitude, north, east);
    const double sigma = std::max(config_.gnss_position_sigma_floor_m,
                                  g.hdop * config_.gnss_hdop_to_sigma_m);
    const bool positionAccepted = updatePositionMeasurementGated(north, east, sigma * sigma);

    bool speedAccepted = false;
    if (g.speed_valid) {
        speedAccepted = updateSpeedMeasurement(
            g.speed_mps,
            std::max(config_.gnss_speed_variance_floor_m2s2, 0.05 * sigma * sigma));
    }
    state_.last_gnss_accepted = positionAccepted || speedAccepted;
    updateNavigationState();
}

void EKFFusionEngine::updateAiSpeed(const AiSpeedMeasurement& speed) {
    state_.last_ai_speed_accepted = false;
    if (!speed.valid || !validMeasurementTime(speed.timestamp) || !finiteValue(speed.velocity_mps) ||
        !finiteValue(speed.variance_m2s2) || speed.velocity_mps < 0.0 ||
        speed.velocity_mps > config_.max_vehicle_speed_mps || speed.variance_m2s2 <= 0.0 ||
        speed.variance_m2s2 > config_.max_speed_variance_m2s2) {
        return;
    }

    state_.last_ai_speed_accepted =
        updateSpeedMeasurement(speed.velocity_mps, speed.variance_m2s2);
    updateNavigationState();
}

void EKFFusionEngine::updateNavigationState() {
    state_.v_x = x_(2);
    state_.v_y = x_(3);
    state_.yaw_rad = normalizeYaw(x_(4));
    if (have_reference_) {
        localToLatLon(x_(0), x_(1), state_.latitude, state_.longitude);
        state_.altitude = reference_altitude_;
    }
    state_.position_cov_m2[0][0] = P_(0, 0);
    state_.position_cov_m2[0][1] = P_(0, 1);
    state_.position_cov_m2[1][0] = P_(1, 0);
    state_.position_cov_m2[1][1] = P_(1, 1);
    state_.valid = finiteVector(x_) && finiteCovariance(P_) &&
                   std::abs(x_(0)) < kMaxReasonableState &&
                   std::abs(x_(1)) < kMaxReasonableState;
}

}  // namespace sih26168::member3
