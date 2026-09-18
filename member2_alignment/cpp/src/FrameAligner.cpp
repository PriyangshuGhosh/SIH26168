#include "member2/FrameAligner.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace sih26168::member2 {
namespace {

bool allFinite(const Eigen::Vector3d& v) {
    return std::isfinite(v.x()) && std::isfinite(v.y()) && std::isfinite(v.z());
}

double clamp01(double x) {
    return std::min(1.0, std::max(0.0, x));
}

double wrapPi(double a) {
    constexpr double kPi = 3.14159265358979323846;
    while (a > kPi) {
        a -= 2.0 * kPi;
    }
    while (a < -kPi) {
        a += 2.0 * kPi;
    }
    return a;
}

int axisSign(double dot, double eps) {
    if (std::abs(dot) <= eps) {
        return 0;
    }
    return (dot > 0.0) ? 1 : -1;
}

bool accelMagnitudesAgree(double a_h_n, double gnss_abs, double rel, double abs_tol) {
    const double hi = std::max(a_h_n, gnss_abs);
    const double lo = std::min(a_h_n, gnss_abs);
    if (hi < 1e-9) {
        return false;
    }
    return (hi <= lo * (1.0 + rel)) && ((hi - lo) <= abs_tol);
}

void storeQuatWxyz(const Eigen::Quaterniond& q, std::array<double, 4>& out) {
    Eigen::Quaterniond n = q.normalized();
    if (n.w() < 0.0) {
        n.coeffs() *= -1.0;
    }
    out[0] = n.w();
    out[1] = n.x();
    out[2] = n.y();
    out[3] = n.z();
}

}  // namespace

Eigen::Vector3d safeNormalize(const Eigen::Vector3d& v, double eps) {
    const double n = v.norm();
    if (n < eps) {
        return Eigen::Vector3d::Zero();
    }
    return v / n;
}

Eigen::Matrix3d rotationZ(double yaw) {
    const double c = std::cos(yaw);
    const double s = std::sin(yaw);
    Eigen::Matrix3d R;
    R << c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0;
    return R;
}

Eigen::Matrix3d rotationGravityUpToVehicleZ(const Eigen::Vector3d& g_up_p) {
    Eigen::Vector3d z = safeNormalize(g_up_p);
    if (z.norm() < 1e-9) {
        return Eigen::Matrix3d::Identity();
    }
    Eigen::Vector3d ref = (std::abs(z.x()) < 0.9) ? Eigen::Vector3d::UnitX() : Eigen::Vector3d::UnitY();
    Eigen::Vector3d y = z.cross(ref);
    if (y.norm() < 1e-9) {
        ref = Eigen::Vector3d::UnitZ();
        y = z.cross(ref);
        if (y.norm() < 1e-9) {
            return Eigen::Matrix3d::Identity();
        }
    }
    y.normalize();
    Eigen::Vector3d x = y.cross(z);
    x = safeNormalize(x);
    Eigen::Matrix3d R;
    R.row(0) = x.transpose();
    R.row(1) = y.transpose();
    R.row(2) = z.transpose();
    return R;
}

Eigen::Quaterniond quatFromRotationMatrix(const Eigen::Matrix3d& R) {
    Eigen::Quaterniond q(R);
    q.normalize();
    if (q.w() < 0.0) {
        q.coeffs() *= -1.0;
    }
    return q;
}

FrameAligner::FrameAligner(const FrameAlignerConfig& config) : cfg_(config) {
    if (cfg_.static_window_samples < 5) {
        cfg_.static_window_samples = 5;
    }
    if (cfg_.static_window_samples > static_cast<int>(kMaxWindow)) {
        cfg_.static_window_samples = static_cast<int>(kMaxWindow);
    }
    reset();
}

void FrameAligner::reset() {
    hist_count_ = 0;
    hist_head_ = 0;
    valid_count_ = 0;
    valid_head_ = 0;
    have_time_ = false;
    t_prev_ = 0.0;
    status_ = CalibrationStatus::UNINITIALIZED;
    g_up_p_ = Eigen::Vector3d::UnitZ();
    g_initialized_ = false;
    have_yaw_ = false;
    yaw_ = 0.0;
    have_yaw_axis_ = false;
    yaw_axis_ = Eigen::Vector2d::UnitX();
    R_vp_ = Eigen::Matrix3d::Identity();
    q_pv_ = Eigen::Quaterniond::Identity();
    scatter_.setZero();
    signed_sum_.setZero();
    axis_evidence_ = 0.0;
    turn_evidence_ = 0.0;
    gnss_sign_evidence_ = 0.0;
    have_last_yaw_update_ = false;
    last_yaw_update_t_ = 0.0;
    have_last_gravity_update_ = false;
    last_gravity_update_t_ = 0.0;
    have_gnss_ = false;
    have_gnss_prev_ = false;
    gnss_accel_ = 0.0;
    sensor_quality_ = 1.0;
    gravity_conf_ = 0.0;
    yaw_conf_ = 0.0;
    static_streak_s_ = 0.0;
}

void FrameAligner::feedGnss(const OptionalGnssAid& aid) {
    gnss_ = aid;
    have_gnss_ = true;
    if (have_gnss_prev_) {
        const double dt = aid.timestamp - gnss_t_prev_;
        if (dt >= 0.005 && dt <= 1.0) {
            const double raw = (aid.speed_mps - gnss_speed_prev_) / dt;
            if (std::isfinite(raw) && std::abs(raw) <= cfg_.gnss_max_abs_accel) {
                gnss_accel_ = 0.3 * raw + 0.7 * gnss_accel_;
            }
        }
    }
    gnss_speed_prev_ = aid.speed_mps;
    gnss_t_prev_ = aid.timestamp;
    have_gnss_prev_ = true;
}

AlignedIMUFrame FrameAligner::process(double timestamp,
                                      double ax_p,
                                      double ay_p,
                                      double az_p,
                                      double gx_p,
                                      double gy_p,
                                      double gz_p) {
    const Eigen::Vector3d acc(ax_p, ay_p, az_p);
    const Eigen::Vector3d gyro(gx_p, gy_p, gz_p);
    const ValidateResult vr = validate(timestamp, acc, gyro);

    valid_hist_[static_cast<std::size_t>(valid_head_)] = vr.ok ? 1 : 0;
    valid_head_ = (valid_head_ + 1) % static_cast<int>(kQualityWindow);
    if (valid_count_ < static_cast<int>(kQualityWindow)) {
        ++valid_count_;
    }
    int ok_n = 0;
    for (int i = 0; i < valid_count_; ++i) {
        ok_n += valid_hist_[static_cast<std::size_t>(i)];
    }
    sensor_quality_ = valid_count_ > 0 ? static_cast<double>(ok_n) / static_cast<double>(valid_count_) : 0.0;

    if (!vr.ok) {
        /* Reject this sample only. Do not latch INVALID on the estimator. */
        CalibrationStatus forced = CalibrationStatus::INVALID;
        return emit(timestamp, acc, gyro, &forced);
    }

    if (vr.gap) {
        hist_count_ = 0;
        hist_head_ = 0;
        static_streak_s_ = 0.0;
        if (status_ == CalibrationStatus::FULLY_ALIGNED || status_ == CalibrationStatus::YAW_UNCERTAIN ||
            status_ == CalibrationStatus::ROLL_PITCH_VALID) {
            status_ = CalibrationStatus::DEGRADED;
        }
    }

    const int cap = cfg_.static_window_samples;
    acc_hist_[static_cast<std::size_t>(hist_head_)] = acc;
    gyro_hist_[static_cast<std::size_t>(hist_head_)] = gyro;
    t_hist_[static_cast<std::size_t>(hist_head_)] = timestamp;
    hist_head_ = (hist_head_ + 1) % cap;
    if (hist_count_ < cap) {
        ++hist_count_;
    }

    const bool is_static = isQuasiStatic();
    if (is_static) {
        static_streak_s_ += (vr.dt > 0.0) ? vr.dt : cfg_.nominal_dt();
        if (status_ == CalibrationStatus::UNINITIALIZED) {
            status_ = CalibrationStatus::STATIC_DETECTED;
        }
        updateGravity(acc, timestamp);
    } else {
        static_streak_s_ = 0.0;
        checkPhoneMoved(acc);
    }

    if (g_initialized_) {
        const double dt = (vr.dt > 0.0) ? vr.dt : cfg_.nominal_dt();
        updateYaw(timestamp, acc, gyro, dt);
    }

    refreshStatus(timestamp);
    rebuildRotation();
    return emit(timestamp, acc, gyro, nullptr);
}

FrameAligner::ValidateResult FrameAligner::validate(double t,
                                                    const Eigen::Vector3d& acc,
                                                    const Eigen::Vector3d& gyro) {
    ValidateResult r;
    if (!std::isfinite(t) || !allFinite(acc) || !allFinite(gyro)) {
        r.hard_invalid = true;
        return r;
    }
    if (acc.norm() > cfg_.max_accel_norm || gyro.norm() > cfg_.max_gyro_norm) {
        r.hard_invalid = true;
        return r;
    }
    if (!have_time_) {
        have_time_ = true;
        t_prev_ = t;
        r.ok = true;
        return r;
    }
    const double dt = t - t_prev_;
    if (dt < 0.0) {
        r.hard_invalid = true;
        return r;
    }
    if (dt < cfg_.min_dt_s) {
        return r;
    }
    r.gap = dt > cfg_.gap_reset_s;
    t_prev_ = t;
    r.dt = dt;
    r.ok = true;
    return r;
}

bool FrameAligner::isQuasiStatic() const {
    const int n = hist_count_;
    const int need = std::max(5, cfg_.static_window_samples / 2);
    if (n < need) {
        return false;
    }
    const int cap = cfg_.static_window_samples;
    const double g = cfg_.gravity_mps2;
    double max_norm_err = 0.0;
    double max_gyro = 0.0;
    Eigen::Vector3d mean = Eigen::Vector3d::Zero();
    Eigen::Vector3d m2 = Eigen::Vector3d::Zero();
    int count = 0;
    double t_oldest = 0.0;
    double t_newest = 0.0;
    const int start = (hist_head_ - n + cap) % cap;
    const double min_dot = g_initialized_ ? std::cos(cfg_.static_dir_align_rad) : 1.0;
    for (int i = 0; i < n; ++i) {
        const int idx = (start + i) % cap;
        const Eigen::Vector3d& a = acc_hist_[static_cast<std::size_t>(idx)];
        const Eigen::Vector3d& w = gyro_hist_[static_cast<std::size_t>(idx)];
        max_norm_err = std::max(max_norm_err, std::abs(a.norm() - g));
        max_gyro = std::max(max_gyro, w.norm());
        if (g_initialized_) {
            const Eigen::Vector3d an = safeNormalize(a);
            if (an.norm() < 1e-9 || an.dot(g_up_p_) < min_dot) {
                return false;
            }
        }
        ++count;
        const Eigen::Vector3d delta = a - mean;
        mean += delta / static_cast<double>(count);
        const Eigen::Vector3d delta2 = a - mean;
        m2 += delta.cwiseProduct(delta2);
        if (i == 0) {
            t_oldest = t_hist_[static_cast<std::size_t>(idx)];
        }
        t_newest = t_hist_[static_cast<std::size_t>(idx)];
    }
    if (max_norm_err > cfg_.static_accel_norm_tol) {
        return false;
    }
    if (max_gyro > cfg_.static_gyro_norm_max) {
        return false;
    }
    const Eigen::Vector3d var = m2 / std::max(1.0, static_cast<double>(count));
    if (var.maxCoeff() > cfg_.static_accel_var_max) {
        return false;
    }
    if (t_newest - t_oldest < 0.5 * cfg_.min_static_duration_s) {
        return false;
    }
    return (static_streak_s_ + cfg_.nominal_dt() >= 0.5 * cfg_.min_static_duration_s) ||
           (n >= cfg_.static_window_samples);
}

void FrameAligner::updateGravity(const Eigen::Vector3d& acc, double t) {
    if (!g_initialized_ && static_streak_s_ < cfg_.min_static_duration_s &&
        hist_count_ < cfg_.static_window_samples) {
        return;
    }
    if (!g_initialized_) {
        Eigen::Vector3d mean = Eigen::Vector3d::Zero();
        const int cap = cfg_.static_window_samples;
        const int start = (hist_head_ - hist_count_ + cap) % cap;
        for (int i = 0; i < hist_count_; ++i) {
            const int idx = (start + i) % cap;
            mean += acc_hist_[static_cast<std::size_t>(idx)];
        }
        mean /= std::max(1, hist_count_);
        g_up_p_ = safeNormalize(mean);
        if (g_up_p_.norm() < 1e-9) {
            return;
        }
        g_initialized_ = true;
        gravity_conf_ = 0.4;
    } else {
        const Eigen::Vector3d prev = g_up_p_;
        const Eigen::Vector3d ema = (1.0 - cfg_.gravity_ema_alpha) * prev + cfg_.gravity_ema_alpha * acc;
        const Eigen::Vector3d nxt = safeNormalize(ema);
        if (nxt.norm() < 1e-9) {
            return;
        }
        const double dot = std::clamp(prev.dot(nxt), -1.0, 1.0);
        const double ang = std::acos(dot);
        if (ang > cfg_.gravity_max_tilt_jump_rad) {
            status_ = CalibrationStatus::REINITIALIZING;
            clearYaw();
            g_up_p_ = nxt;
        } else {
            g_up_p_ = nxt;
        }
        gravity_conf_ = clamp01(gravity_conf_ * 0.98 + 0.02 * (1.0 - ang / 0.5));
    }
    have_last_gravity_update_ = true;
    last_gravity_update_t_ = t;
    if (status_ == CalibrationStatus::UNINITIALIZED || status_ == CalibrationStatus::STATIC_DETECTED ||
        status_ == CalibrationStatus::REINITIALIZING) {
        status_ = CalibrationStatus::ROLL_PITCH_VALID;
    }
}

void FrameAligner::checkPhoneMoved(const Eigen::Vector3d& acc) {
    if (!g_initialized_) {
        return;
    }
    const double an = acc.norm();
    if (an < 1.0) {
        return;
    }
    const Eigen::Vector3d up_meas = acc / an;
    const double dot = std::clamp(g_up_p_.dot(up_meas), -1.0, 1.0);
    const double ang = std::acos(dot);
    if (ang > 0.6 &&
        (status_ == CalibrationStatus::FULLY_ALIGNED || status_ == CalibrationStatus::YAW_UNCERTAIN ||
         status_ == CalibrationStatus::ROLL_PITCH_VALID)) {
        if (std::abs(an - cfg_.gravity_mps2) < 2.5) {
            status_ = CalibrationStatus::REINITIALIZING;
            clearYaw();
            g_initialized_ = false;
            gravity_conf_ = 0.0;
        }
    }
}

void FrameAligner::clearYaw() {
    have_yaw_ = false;
    have_yaw_axis_ = false;
    scatter_.setZero();
    signed_sum_.setZero();
    axis_evidence_ = 0.0;
    turn_evidence_ = 0.0;
    gnss_sign_evidence_ = 0.0;
    yaw_conf_ = 0.0;
    have_last_yaw_update_ = false;
}

bool FrameAligner::gnssQualityOk(double t) const {
    if (!have_gnss_) {
        return false;
    }
    if ((t - gnss_.timestamp) > cfg_.gnss_max_age_s) {
        return false;
    }
    if (gnss_.hdop > cfg_.gnss_max_hdop || gnss_.num_sats < cfg_.gnss_min_sats) {
        return false;
    }
    if (gnss_.speed_mps < 0.0 || !std::isfinite(gnss_.speed_mps) || !std::isfinite(gnss_.hdop)) {
        return false;
    }
    return true;
}

bool FrameAligner::gnssSignReady(double t, double a_h_n) const {
    if (!gnssQualityOk(t)) {
        return false;
    }
    if (gnss_.speed_mps < cfg_.gnss_min_speed_mps) {
        return false;
    }
    const double mag = std::abs(gnss_accel_);
    if (mag < cfg_.gnss_min_accel || mag > cfg_.gnss_max_abs_accel) {
        return false;
    }
    return accelMagnitudesAgree(a_h_n, mag, cfg_.gnss_imu_agree_rel, cfg_.gnss_imu_agree_abs);
}

void FrameAligner::updateYaw(double t,
                             const Eigen::Vector3d& acc_p,
                             const Eigen::Vector3d& gyro_p,
                             double dt) {
    const Eigen::Matrix3d R_gp = rotationGravityUpToVehicleZ(g_up_p_);
    const Eigen::Vector3d acc_g = R_gp * acc_p;
    const Eigen::Vector3d gyro_g = R_gp * gyro_p;
    const Eigen::Vector2d a_h(acc_g.x(), acc_g.y());
    const double a_h_n = a_h.norm();
    const double gyro_n = gyro_g.norm();
    const double acc_n = acc_g.norm();
    if (acc_n > cfg_.yaw_shock_accel_max) {
        return;
    }
    const bool straight = gyro_n < cfg_.yaw_max_gyro_norm;
    if (straight && a_h_n >= cfg_.yaw_min_horiz_accel) {
        const bool gnss_watch = gnssQualityOk(t) && gnss_.speed_mps >= cfg_.gnss_min_speed_mps;
        const bool gnss_sign_ok = gnssSignReady(t, a_h_n);
        const bool skip_non_long = gnss_watch && !gnss_sign_ok;
        if (!skip_non_long) {
            scatter_ += (a_h * a_h.transpose()) * dt;
            axis_evidence_ += a_h_n * dt;
            if (gnss_sign_ok) {
                const double sgn = (gnss_accel_ >= 0.0) ? 1.0 : -1.0;
                signed_sum_ += sgn * a_h * dt;
                gnss_sign_evidence_ += std::abs(gnss_accel_) * dt;
            }
            have_last_yaw_update_ = true;
            last_yaw_update_t_ = t;
        }
    }
    Eigen::Vector2d axis;
    if (principalAxis(axis) && gyro_n >= cfg_.yaw_turn_gyro_min && a_h_n >= 0.25) {
        const double wz = gyro_g.z();
        const Eigen::Vector2d nlat(-axis.y(), axis.x());
        const double lat = a_h.dot(nlat);
        turn_evidence_ += ((wz >= 0.0) ? 1.0 : -1.0) * lat * dt;
        have_last_yaw_update_ = true;
        last_yaw_update_t_ = t;
    }
    maybeLockYaw(t);
}

bool FrameAligner::principalAxis(Eigen::Vector2d& axis_out) const {
    if (axis_evidence_ < 0.25 * cfg_.yaw_min_evidence) {
        return false;
    }
    Eigen::SelfAdjointEigenSolver<Eigen::Matrix2d> es(scatter_);
    if (es.info() != Eigen::Success) {
        return false;
    }
    const Eigen::Vector2d w = es.eigenvalues();
    if (w(1) <= 1e-12) {
        return false;
    }
    const double ratio = w(1) / std::max(w(0), 1e-12);
    if (ratio < cfg_.yaw_pca_ratio_min) {
        return false;
    }
    axis_out = es.eigenvectors().col(1);
    return true;
}

void FrameAligner::maybeLockYaw(double t) {
    Eigen::Vector2d axis;
    if (!principalAxis(axis) || axis_evidence_ < cfg_.yaw_min_evidence) {
        return;
    }
    have_yaw_axis_ = true;
    yaw_axis_ = axis;
    const double signed_n = signed_sum_.norm();
    const int s_gnss = (gnss_sign_evidence_ >= cfg_.gnss_sign_evidence_min && signed_n > 1e-6)
                           ? axisSign(signed_sum_.dot(axis), 1e-9)
                           : 0;
    const int s_turn = (std::abs(turn_evidence_) >= cfg_.yaw_turn_evidence_min)
                           ? axisSign(turn_evidence_, 1e-12)
                           : 0;
    if (s_gnss != 0 && s_turn != 0 && s_gnss != s_turn) {
        have_yaw_ = false;
        yaw_conf_ = std::min(yaw_conf_, 0.25);
        return;
    }
    const double sign = static_cast<double>(s_gnss != 0 ? s_gnss : s_turn);
    if (sign == 0.0) {
        yaw_conf_ = clamp01(axis_evidence_ / (cfg_.yaw_min_evidence * 3.0));
        yaw_conf_ = std::min(yaw_conf_, 0.45);
        return;
    }
    const Eigen::Vector2d u = sign * axis;
    const double yaw_new = -std::atan2(u.y(), u.x());
    if (have_yaw_) {
        const double d = std::abs(wrapPi(yaw_new - yaw_));
        if (d > cfg_.yaw_disagree_rad) {
            have_yaw_ = false;
            yaw_conf_ = std::min(yaw_conf_, 0.30);
            return;
        }
    }
    yaw_ = yaw_new;
    have_yaw_ = true;
    const double c_axis = std::min(1.0, axis_evidence_ / (cfg_.yaw_min_evidence * 2.5));
    const double c_turn = std::min(1.0, std::abs(turn_evidence_) / std::max(cfg_.yaw_turn_evidence_min * 2.0, 1e-6));
    const double c_gnss = std::min(1.0, gnss_sign_evidence_ / 1.5);
    yaw_conf_ = clamp01(0.35 * c_axis + 0.35 * c_turn + 0.30 * c_gnss);
    if (gnss_sign_evidence_ < cfg_.gnss_sign_evidence_min) {
        yaw_conf_ = std::min(yaw_conf_, 0.85);
    }
    have_last_yaw_update_ = true;
    last_yaw_update_t_ = t;
}

void FrameAligner::refreshStatus(double t) {
    if (status_ == CalibrationStatus::INVALID) {
        return;
    }
    if (!g_initialized_) {
        if (status_ != CalibrationStatus::UNINITIALIZED && status_ != CalibrationStatus::STATIC_DETECTED &&
            status_ != CalibrationStatus::REINITIALIZING) {
            status_ = CalibrationStatus::UNINITIALIZED;
        }
        return;
    }
    bool yaw_stale = false;
    if (have_last_yaw_update_) {
        yaw_stale = (t - last_yaw_update_t_) > cfg_.yaw_hold_s * 2.0;
    }
    if (have_yaw_ && yaw_stale) {
        have_yaw_ = false;
        yaw_conf_ = std::min(yaw_conf_, 0.30);
    }
    if (have_yaw_ && yaw_conf_ >= 0.35 && !yaw_stale) {
        status_ = CalibrationStatus::FULLY_ALIGNED;
        const CalibrationConfidence conf = composeConfidence();
        if (conf.overall < cfg_.fully_aligned_min_confidence) {
            status_ = CalibrationStatus::YAW_UNCERTAIN;
        }
    } else if (have_yaw_axis_) {
        status_ = CalibrationStatus::YAW_UNCERTAIN;
    } else if (status_ == CalibrationStatus::REINITIALIZING) {
        status_ = CalibrationStatus::ROLL_PITCH_VALID;
    } else if (status_ != CalibrationStatus::DEGRADED) {
        status_ = CalibrationStatus::ROLL_PITCH_VALID;
    }
}

void FrameAligner::rebuildRotation() {
    if (!g_initialized_) {
        R_vp_ = Eigen::Matrix3d::Identity();
        q_pv_ = Eigen::Quaterniond::Identity();
        return;
    }
    const Eigen::Matrix3d R_gp = rotationGravityUpToVehicleZ(g_up_p_);
    if (have_yaw_ && (status_ == CalibrationStatus::FULLY_ALIGNED || status_ == CalibrationStatus::DEGRADED)) {
        R_vp_ = rotationZ(yaw_) * R_gp;
    } else {
        R_vp_ = R_gp;
    }
    q_pv_ = quatFromRotationMatrix(R_vp_);
}

CalibrationConfidence FrameAligner::composeConfidence() const {
    double g_temp = 0.0;
    if (have_last_gravity_update_ && have_time_) {
        g_temp = clamp01(1.0 - (t_prev_ - last_gravity_update_t_) / 30.0);
    }
    double y_temp = 0.0;
    if (have_last_yaw_update_) {
        y_temp = clamp01(1.0 - (t_prev_ - last_yaw_update_t_) / cfg_.yaw_hold_s);
    }
    const double temporal = 0.6 * g_temp + 0.4 * y_temp;
    const double g = g_initialized_ ? gravity_conf_ : 0.0;
    double y = 0.0;
    if (have_yaw_) {
        y = yaw_conf_;
    } else if (have_yaw_axis_) {
        y = std::min(0.4, axis_evidence_ / std::max(cfg_.yaw_min_evidence, 1e-6) * 0.2);
    }
    const double s = sensor_quality_;
    double overall = 0.0;
    if (status_ == CalibrationStatus::FULLY_ALIGNED) {
        overall = 0.30 * g + 0.45 * y + 0.15 * temporal + 0.10 * s;
    } else if (status_ == CalibrationStatus::YAW_UNCERTAIN) {
        overall = std::min(cfg_.yaw_uncertain_confidence_cap, 0.70 * g + 0.10 * y + 0.10 * temporal + 0.10 * s);
    } else if (status_ == CalibrationStatus::ROLL_PITCH_VALID || status_ == CalibrationStatus::DEGRADED) {
        overall = std::min(0.50, 0.75 * g + 0.05 * y + 0.10 * temporal + 0.10 * s);
    } else if (status_ == CalibrationStatus::STATIC_DETECTED) {
        overall = std::min(0.25, 0.5 * s);
    } else {
        overall = std::min(0.15, 0.5 * s);
    }
    if (status_ == CalibrationStatus::UNINITIALIZED) {
        overall = 0.0;
    } else if (status_ == CalibrationStatus::INVALID) {
        overall = std::min(overall, 0.05);
    }
    CalibrationConfidence c;
    c.overall = clamp01(overall);
    c.gravity = clamp01(g);
    c.yaw_observability = clamp01(y);
    c.temporal = clamp01(temporal);
    c.sensor_quality = clamp01(s);
    return c;
}

AlignedIMUFrame FrameAligner::emit(double t,
                                   const Eigen::Vector3d& acc_p,
                                   const Eigen::Vector3d& gyro_p,
                                   const CalibrationStatus* force_status) const {
    Eigen::Vector3d acc_v = acc_p;
    Eigen::Vector3d gyro_v = gyro_p;
    if (allFinite(acc_p) && allFinite(gyro_p)) {
        acc_v = R_vp_ * acc_p;
        gyro_v = R_vp_ * gyro_p;
    }
    AlignedIMUFrame frame;
    frame.timestamp = t;
    frame.ax_v = acc_v.x();
    frame.ay_v = acc_v.y();
    frame.az_v = acc_v.z();
    frame.gx_v = gyro_v.x();
    frame.gy_v = gyro_v.y();
    frame.gz_v = gyro_v.z();
    storeQuatWxyz(q_pv_, frame.q_pv);
    frame.status = force_status != nullptr ? *force_status : status_;
    frame.confidence = composeConfidence();
    if (frame.status == CalibrationStatus::INVALID) {
        frame.confidence.overall = std::min(frame.confidence.overall, 0.05);
    }
    return frame;
}

}  // namespace sih26168::member2
