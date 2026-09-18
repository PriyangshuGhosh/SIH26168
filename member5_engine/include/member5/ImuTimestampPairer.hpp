#pragma once

#include <cmath>
#include <optional>

namespace sih26168::member5 {

/* Pairs independent accel/gyro callbacks by timestamp. Host tests cover this;
   Android ImuService uses the same pairing rule before idr_feed_imu. */
struct PairedImuSample {
    double timestamp_s{0.0};
    double ax{0.0};
    double ay{0.0};
    double az{0.0};
    double gx{0.0};
    double gy{0.0};
    double gz{0.0};
};

class ImuTimestampPairer {
public:
    explicit ImuTimestampPairer(double max_skew_s = 0.008) : max_skew_s_(max_skew_s) {}

    void reset() {
        have_accel_ = false;
        have_gyro_ = false;
        last_out_t_ = 0.0;
        have_out_ = false;
    }

    std::optional<PairedImuSample> feedAccel(double timestamp_s, double ax, double ay, double az) {
        if (!std::isfinite(timestamp_s) || !std::isfinite(ax) || !std::isfinite(ay) ||
            !std::isfinite(az)) {
            return std::nullopt;
        }
        accel_t_ = timestamp_s;
        ax_ = ax;
        ay_ = ay;
        az_ = az;
        have_accel_ = true;
        return maybeEmit();
    }

    std::optional<PairedImuSample> feedGyro(double timestamp_s, double gx, double gy, double gz) {
        if (!std::isfinite(timestamp_s) || !std::isfinite(gx) || !std::isfinite(gy) ||
            !std::isfinite(gz)) {
            return std::nullopt;
        }
        gyro_t_ = timestamp_s;
        gx_ = gx;
        gy_ = gy;
        gz_ = gz;
        have_gyro_ = true;
        return maybeEmit();
    }

private:
    std::optional<PairedImuSample> maybeEmit() {
        if (!have_accel_ || !have_gyro_) {
            return std::nullopt;
        }
        const double dt = std::abs(accel_t_ - gyro_t_);
        if (dt > max_skew_s_) {
            return std::nullopt;
        }
        const double t = 0.5 * (accel_t_ + gyro_t_);
        if (have_out_ && t <= last_out_t_) {
            return std::nullopt;
        }
        have_out_ = true;
        last_out_t_ = t;
        PairedImuSample s;
        s.timestamp_s = t;
        s.ax = ax_;
        s.ay = ay_;
        s.az = az_;
        s.gx = gx_;
        s.gy = gy_;
        s.gz = gz_;
        return s;
    }

    double max_skew_s_{0.008};
    bool have_accel_{false};
    bool have_gyro_{false};
    double accel_t_{0.0};
    double gyro_t_{0.0};
    double ax_{0.0}, ay_{0.0}, az_{0.0};
    double gx_{0.0}, gy_{0.0}, gz_{0.0};
    bool have_out_{false};
    double last_out_t_{0.0};
};

inline double sensorEventNsToSeconds(long long timestamp_ns) {
    return static_cast<double>(timestamp_ns) * 1.0e-9;
}

}  // namespace sih26168::member5
