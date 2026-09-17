#include "idr_engine_api.h"
#include "test_support.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <string>
#include <thread>

int main() {
    const std::string pack = sih26168_find_roadpack();
    if (idr_engine_init(pack.c_str(), "mock") != 1) {
        std::fprintf(stderr, "init failed: %s\n", idr_engine_last_error());
        return 1;
    }

    constexpr int kIters = 20000;
    const auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < kIters; ++i) {
        idr_feed_gnss(1.0, 12.97, 77.59, 920.0, 10.0, 1.0, 8);
        idr_feed_gnss(1.0, 12.97, 77.59, 920.0, 10.0, 9.0, 8);
    }
    const auto t1 = std::chrono::steady_clock::now();
    const double us = std::chrono::duration<double, std::micro>(t1 - t0).count() / (kIters * 2.0);

    /* Complete native pipeline at 100 Hz IMU (explicit mock speed; real M2/M3/M4). */
    constexpr int kImu = 2000;
    const auto p0 = std::chrono::steady_clock::now();
    for (int i = 0; i < kImu; ++i) {
        const double t = 10.0 + 0.01 * i;
        if (i % 100 == 0) {
            idr_feed_gnss(t, 12.9716 + (0.08 * i) / 111320.0, 77.5946, 920.0, 8.0, 1.1, 9);
        }
        idr_feed_imu(t, 0.2, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    /* Drain worker. */
    for (int w = 0; w < 200; ++w) {
        if (idr_get_current_state().timestamp + 1e-4 >= 10.0 + 0.01 * (kImu - 1)) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    const auto p1 = std::chrono::steady_clock::now();
    const double imu_us =
        std::chrono::duration<double, std::micro>(p1 - p0).count() / static_cast<double>(kImu);
    const double imu_hz = 1.0e6 / imu_us;

    IDRNavigationOutput s = idr_get_current_state();
    std::printf("mean_feed_gnss_mode_switch_us=%.3f last_dr=%d\n", us, s.is_dead_reckoning);
    std::printf("pipeline_feed_imu_mean_us=%.3f throughput_hz=%.1f sustains_100hz=%d\n", imu_us,
                imu_hz, imu_us < 10000.0 ? 1 : 0);
    std::printf("backend=%s road_segment_id=%lld on_road=%d\n", idr_engine_speed_backend(),
                idr_get_road_segment_id(), idr_is_on_road_network());
    std::printf("target_us=10000 (handbook <10 ms GNSS deficit transition)\n");
    std::printf("speed_estimator=explicit_mock (no silent production fallback)\n");
    idr_engine_shutdown();
    return (us < 10000.0 && imu_us < 10000.0 && std::isfinite(us) && std::isfinite(imu_us)) ? 0 : 1;
}
