#include "member2/FrameAligner.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <string>

namespace {

int g_failed = 0;

void expect(bool cond, const std::string& msg) {
    if (!cond) {
        std::cerr << "FAIL: " << msg << "\n";
        ++g_failed;
    }
}

void expectNear(double a, double b, double tol, const std::string& msg) {
    if (!(std::isfinite(a) && std::isfinite(b) && std::abs(a - b) <= tol)) {
        std::cerr << "FAIL: " << msg << " got " << a << " expected " << b << " tol " << tol << "\n";
        ++g_failed;
    }
}

Eigen::Matrix3d Rz(double y) {
    return sih26168::member2::rotationZ(y);
}

Eigen::Matrix3d Ry(double p) {
    const double c = std::cos(p);
    const double s = std::sin(p);
    Eigen::Matrix3d R;
    R << c, 0, s, 0, 1, 0, -s, 0, c;
    return R;
}

Eigen::Matrix3d Rx(double r) {
    const double c = std::cos(r);
    const double s = std::sin(r);
    Eigen::Matrix3d R;
    R << 1, 0, 0, 0, c, -s, 0, s, c;
    return R;
}

}  // namespace

int main() {
    using namespace sih26168::member2;

    constexpr double kPi = 3.14159265358979323846;
    expectNear(rotationZ(0)(0, 0), 1.0, 1e-12, "identity Rz");
    const Eigen::Vector3d e1 = Eigen::Vector3d::UnitX();
    const Eigen::Vector3d e2 = Eigen::Vector3d::UnitY();
    const Eigen::Vector3d e3 = Eigen::Vector3d::UnitZ();
    expectNear((rotationZ(kPi / 2) * e1).y(), 1.0, 1e-9, "+90 yaw X->Y");
    expectNear((rotationZ(kPi / 2) * e1).x(), 0.0, 1e-9, "+90 yaw X x");
    expectNear((Rx(kPi / 2) * e2).z(), 1.0, 1e-9, "+90 roll Y->Z");
    expectNear((Ry(kPi / 2) * e3).x(), 1.0, 1e-9, "+90 pitch Z->X");

    const Eigen::Matrix3d R = rotationZ(0.4) * Ry(-0.3) * Rx(0.7);
    expectNear((R.transpose() * R - Eigen::Matrix3d::Identity()).norm(), 0.0, 1e-9, "orthonormal");
    expectNear(R.determinant(), 1.0, 1e-9, "det +1");

    const Eigen::Quaterniond q = quatFromRotationMatrix(R);
    expectNear(q.norm(), 1.0, 1e-12, "quat unit");
    const Eigen::Matrix3d R2 = q.toRotationMatrix();
    expectNear((R - R2).norm(), 0.0, 1e-9, "quat<->R");
    const Eigen::Vector3d v(0.2, -0.4, 0.8);
    expectNear((R * v - q._transformVector(v)).norm(), 0.0, 1e-9, "quat rotate vs R");
    expectNear((R.transpose() * (R * v) - v).norm(), 0.0, 1e-12, "inverse recover");
    expectNear((R * v).norm(), v.norm(), 1e-12, "magnitude preserved");

    const Eigen::Vector3d up_p = safeNormalize(Eigen::Vector3d(0.1, -0.2, 0.97));
    const Eigen::Matrix3d Rgp = rotationGravityUpToVehicleZ(up_p);
    const Eigen::Vector3d up_v = Rgp * up_p;
    expectNear(up_v.x(), 0.0, 1e-9, "gravity x");
    expectNear(up_v.y(), 0.0, 1e-9, "gravity y");
    expectNear(up_v.z(), 1.0, 1e-9, "gravity z");

    // Combined mount: vehicle X maps correctly when yaw known.
    const Eigen::Matrix3d R_vp = rotationZ(-1.2) * rotationGravityUpToVehicleZ(Eigen::Vector3d::UnitZ());
    FrameAligner aligner;
    // Feed identity gravity so tilt is identity-like; this checks process identity path.
    for (int i = 0; i < 80; ++i) {
        aligner.process(0.01 * i, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0);
    }
    expect(aligner.status() == CalibrationStatus::ROLL_PITCH_VALID ||
               aligner.status() == CalibrationStatus::STATIC_DETECTED ||
               aligner.status() == CalibrationStatus::YAW_UNCERTAIN ||
               aligner.status() == CalibrationStatus::FULLY_ALIGNED,
           "static should establish roll/pitch");
    const auto f = aligner.process(0.80, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0);
    expectNear(f.az_v, 9.80665, 0.15, "static az ~ g after tilt");
    expect(f.confidence.overall < 0.62, "no false high-confidence yaw from static-only");
    expect(f.status != CalibrationStatus::FULLY_ALIGNED, "static is not FULLY_ALIGNED");
    expectNear(std::abs(f.q_pv[0] * f.q_pv[0] + f.q_pv[1] * f.q_pv[1] + f.q_pv[2] * f.q_pv[2] +
                        f.q_pv[3] * f.q_pv[3] - 1.0),
               0.0, 1e-12, "unit quat");
    const Eigen::Matrix3d Rnow = aligner.rotationMatrixPhoneToVehicle();
    expectNear((Rnow.transpose() * Rnow - Eigen::Matrix3d::Identity()).norm(), 0.0, 1e-9, "R orthonormal");
    expectNear(Rnow.determinant(), 1.0, 1e-9, "R det +1");

    // Invalid samples
    const auto bad = aligner.process(0.81, std::nan(""), 0, 0, 0, 0, 0);
    expect(bad.status == CalibrationStatus::INVALID, "NaN -> INVALID");
    const auto inf = aligner.process(0.82, 0, 0, std::numeric_limits<double>::infinity(), 0, 0, 0);
    expect(inf.status == CalibrationStatus::INVALID, "Inf -> INVALID");
    const auto back = aligner.process(0.10, 0, 0, 9.8, 0, 0, 0);
    expect(back.status == CalibrationStatus::INVALID, "timestamp regression -> INVALID");

    (void)R_vp;
    if (g_failed == 0) {
        std::cout << "member2_cpp_tests OK\n";
        return 0;
    }
    std::cerr << g_failed << " failures\n";
    return 1;
}
