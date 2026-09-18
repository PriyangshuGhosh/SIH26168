#pragma once

#include "member2/calibration_types.h"

#include <Eigen/Dense>
#include <array>
#include <cstddef>
#include <cstdint>

namespace sih26168::member2 {

class FrameAligner {
public:
    static constexpr std::size_t kMaxWindow = 256;
    static constexpr std::size_t kQualityWindow = 100;

    explicit FrameAligner(const FrameAlignerConfig& config = FrameAlignerConfig{});

    void reset();

    AlignedIMUFrame process(double timestamp,
                            double ax_p,
                            double ay_p,
                            double az_p,
                            double gx_p,
                            double gy_p,
                            double gz_p);

    void feedGnss(const OptionalGnssAid& aid);

    CalibrationStatus status() const { return status_; }
    CalibrationConfidence confidence() const { return composeConfidence(); }
    Eigen::Matrix3d rotationMatrixPhoneToVehicle() const { return R_vp_; }
    Eigen::Quaterniond quatPhoneToVehicle() const { return q_pv_; }

    Eigen::Vector3d phoneToVehicleVector(const Eigen::Vector3d& vec_p) const {
        return R_vp_ * vec_p;
    }
    Eigen::Vector3d vehicleToPhoneVector(const Eigen::Vector3d& vec_v) const {
        return R_vp_.transpose() * vec_v;
    }

    const FrameAlignerConfig& config() const { return cfg_; }

private:
    struct ValidateResult {
        bool ok{false};
        bool hard_invalid{false};
        double dt{0.0};
        bool gap{false};
    };

    ValidateResult validate(double t, const Eigen::Vector3d& acc, const Eigen::Vector3d& gyro);
    bool isQuasiStatic() const;
    void updateGravity(const Eigen::Vector3d& acc, double t);
    void checkPhoneMoved(const Eigen::Vector3d& acc);
    void clearYaw();
    bool gnssQualityOk(double t) const;
    bool gnssSignReady(double t, double a_h_n) const;
    void updateYaw(double t, const Eigen::Vector3d& acc_p, const Eigen::Vector3d& gyro_p, double dt);
    bool principalAxis(Eigen::Vector2d& axis_out) const;
    void maybeLockYaw(double t);
    void refreshStatus(double t);
    void rebuildRotation();
    CalibrationConfidence composeConfidence() const;
    AlignedIMUFrame emit(double t,
                         const Eigen::Vector3d& acc_p,
                         const Eigen::Vector3d& gyro_p,
                         const CalibrationStatus* force_status) const;

    FrameAlignerConfig cfg_;

    std::array<Eigen::Vector3d, kMaxWindow> acc_hist_{};
    std::array<Eigen::Vector3d, kMaxWindow> gyro_hist_{};
    std::array<double, kMaxWindow> t_hist_{};
    int hist_count_{0};
    int hist_head_{0};

    std::array<std::uint8_t, kQualityWindow> valid_hist_{};
    int valid_count_{0};
    int valid_head_{0};

    bool have_time_{false};
    double t_prev_{0.0};

    CalibrationStatus status_{CalibrationStatus::UNINITIALIZED};
    Eigen::Vector3d g_up_p_{Eigen::Vector3d::UnitZ()};
    bool g_initialized_{false};
    bool have_yaw_{false};
    double yaw_{0.0};
    bool have_yaw_axis_{false};
    Eigen::Vector2d yaw_axis_{Eigen::Vector2d::UnitX()};
    Eigen::Matrix3d R_vp_{Eigen::Matrix3d::Identity()};
    Eigen::Quaterniond q_pv_{Eigen::Quaterniond::Identity()};

    Eigen::Matrix2d scatter_{Eigen::Matrix2d::Zero()};
    Eigen::Vector2d signed_sum_{Eigen::Vector2d::Zero()};
    double axis_evidence_{0.0};
    double turn_evidence_{0.0};
    double gnss_sign_evidence_{0.0};
    bool have_last_yaw_update_{false};
    double last_yaw_update_t_{0.0};
    bool have_last_gravity_update_{false};
    double last_gravity_update_t_{0.0};

    bool have_gnss_{false};
    OptionalGnssAid gnss_{};
    bool have_gnss_prev_{false};
    double gnss_speed_prev_{0.0};
    double gnss_t_prev_{0.0};
    double gnss_accel_{0.0};

    double sensor_quality_{1.0};
    double gravity_conf_{0.0};
    double yaw_conf_{0.0};
    double static_streak_s_{0.0};
};

Eigen::Matrix3d rotationGravityUpToVehicleZ(const Eigen::Vector3d& g_up_p);
Eigen::Matrix3d rotationZ(double yaw);
Eigen::Quaterniond quatFromRotationMatrix(const Eigen::Matrix3d& R);
Eigen::Vector3d safeNormalize(const Eigen::Vector3d& v, double eps = 1e-12);

}  // namespace sih26168::member2
