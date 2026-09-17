#include "member2/FrameAligner.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

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

sih26168::member2::AlignedIMUFrame staticGravity(sih26168::member2::FrameAligner& a, double t) {
    return a.process(t, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0);
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

    FrameAligner aligner;
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

    const auto bad = aligner.process(0.81, std::nan(""), 0, 0, 0, 0, 0);
    expect(bad.status == CalibrationStatus::INVALID, "NaN -> INVALID");
    const auto inf = aligner.process(0.82, 0, 0, std::numeric_limits<double>::infinity(), 0, 0, 0);
    expect(inf.status == CalibrationStatus::INVALID, "Inf -> INVALID");
    const auto back = aligner.process(0.10, 0, 0, 9.8, 0, 0, 0);
    expect(back.status == CalibrationStatus::INVALID, "timestamp regression -> INVALID");

    /* 100 Hz labelled synthetic (phone already gravity-aligned; not recorded driving). */
    {
        FrameAligner a;
        int accepted = 0;
        constexpr int n = 500;
        for (int i = 0; i < n; ++i) {
            const auto o = a.process(0.01 * i, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0);
            if (o.status != CalibrationStatus::INVALID) {
                ++accepted;
            }
            expect(std::isfinite(o.ax_v) && std::isfinite(o.az_v), "100Hz finite");
            expectNear(o.timestamp, 0.01 * i, 1e-12, "timestamp echo");
        }
        expect(accepted == n, "all 100 Hz samples accepted");
    }

    /* Jitter around 100 Hz. */
    {
        FrameAligner a;
        double t = 0.0;
        int accepted = 0;
        for (int i = 0; i < 200; ++i) {
            const double dt = (i % 3 == 0) ? 0.007 : ((i % 3 == 1) ? 0.013 : 0.010);
            t += (i == 0) ? 0.0 : dt;
            const auto o = staticGravity(a, t);
            if (o.status != CalibrationStatus::INVALID) {
                ++accepted;
            }
        }
        expect(accepted == 200, "jittered timestamps accepted");
    }

    /* Dropped samples (gap < 1 s): still causal, no invented IMU). */
    {
        FrameAligner a;
        for (int i = 0; i < 50; ++i) {
            staticGravity(a, 0.01 * i);
        }
        const auto after_drop = staticGravity(a, 0.50 + 0.20);
        expect(after_drop.status != CalibrationStatus::INVALID, "short drop still valid");
        expectNear(after_drop.timestamp, 0.70, 1e-12, "drop timestamp");
    }

    /* Duplicates / sub-dt: rejected, history not advanced as a new measurement. */
    {
        FrameAligner a;
        staticGravity(a, 1.00);
        const auto dup = staticGravity(a, 1.00);
        expect(dup.status == CalibrationStatus::INVALID, "duplicate timestamp INVALID");
        const auto next = staticGravity(a, 1.01);
        expect(next.status != CalibrationStatus::INVALID, "in-order after duplicate");
    }

    /* Out-of-order: INVALID then resume. */
    {
        FrameAligner a;
        staticGravity(a, 2.00);
        const auto ooo = staticGravity(a, 1.90);
        expect(ooo.status == CalibrationStatus::INVALID, "OOO INVALID");
        const auto resume = staticGravity(a, 2.01);
        expect(resume.status != CalibrationStatus::INVALID, "resume after OOO");
    }

    /* Long stream + deterministic replay. */
    {
        auto run = [] {
            FrameAligner a;
            std::vector<AlignedIMUFrame> out;
            out.reserve(2000);
            for (int i = 0; i < 2000; ++i) {
                const double t = 0.01 * i;
                const double ax = 0.05 * std::sin(0.03 * i);
                out.push_back(a.process(t, ax, 0.0, 9.80665, 0.0, 0.0, 0.0));
            }
            return out;
        };
        const auto a = run();
        const auto b = run();
        expect(a.size() == b.size(), "deterministic length");
        for (std::size_t i = 0; i < a.size(); ++i) {
            expectNear(a[i].ax_v, b[i].ax_v, 0.0, "deterministic ax");
            expectNear(a[i].az_v, b[i].az_v, 0.0, "deterministic az");
            expect(a[i].status == b[i].status, "deterministic status");
            expect(std::isfinite(a[i].q_pv[0]), "quat finite long stream");
        }
    }

    /* Member 1 window: channel order [ax,ay,az,gx,gy,gz], 200 samples at 100 Hz (2 s). */
    {
        FrameAligner a;
        float window[6 * 200]{};
        for (int i = 0; i < 200; ++i) {
            const auto o = a.process(0.01 * i, 0.1, -0.2, 9.80665, 0.01, -0.02, 0.03);
            expect(o.status != CalibrationStatus::INVALID, "M1 window sample");
            window[0 * 200 + i] = static_cast<float>(o.ax_v);
            window[1 * 200 + i] = static_cast<float>(o.ay_v);
            window[2 * 200 + i] = static_cast<float>(o.az_v);
            window[3 * 200 + i] = static_cast<float>(o.gx_v);
            window[4 * 200 + i] = static_cast<float>(o.gy_v);
            window[5 * 200 + i] = static_cast<float>(o.gz_v);
        }
        for (int k = 0; k < 6 * 200; ++k) {
            expect(std::isfinite(window[k]), "M1 window finite");
        }
        expect(window[2 * 200 + 199] > 8.0f, "az channel is gravity-ish");
    }

    /* Member 1 live ONNX packing: time-major [T,6] at 100 Hz, T=200, no decimation. */
    {
        FrameAligner a;
        float win[200 * 6]{};
        for (int i = 0; i < 200; ++i) {
            const auto o = a.process(0.01 * i, 0.15, 0.0, 9.80665, 0.0, 0.0, 0.0);
            expect(o.status != CalibrationStatus::INVALID, "100Hz pack sample");
            win[i * 6 + 0] = static_cast<float>(o.ax_v);
            win[i * 6 + 1] = static_cast<float>(o.ay_v);
            win[i * 6 + 2] = static_cast<float>(o.az_v);
            win[i * 6 + 3] = static_cast<float>(o.gx_v);
            win[i * 6 + 4] = static_cast<float>(o.gy_v);
            win[i * 6 + 5] = static_cast<float>(o.gz_v);
        }
        expect(win[2] > 8.0f && win[199 * 6 + 2] > 8.0f, "100Hz az gravity-ish");
    }

    /* Member 3 field contract: AlignedIMUFrame remains finite for EKF predict. */
    {
        FrameAligner a;
        AlignedIMUFrame last{};
        for (int i = 0; i < 100; ++i) {
            last = a.process(0.01 * i, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0);
        }
        expect(std::isfinite(last.ax_v) && std::isfinite(last.ay_v) && std::isfinite(last.gz_v),
               "M3 IMU fields finite");
        expect(last.timestamp >= 0.0, "M3 timestamp");
    }

    if (g_failed == 0) {
        std::cout << "member2_cpp_tests OK\n";
        return 0;
    }
    std::cerr << g_failed << " failures\n";
    return 1;
}
