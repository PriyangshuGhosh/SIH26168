#include "idr_engine_api.h"
#include "test_support.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <thread>

/* Host-only replay. Every line is labelled SIMULATION. Not phone sensors. */

int main() {
    const std::string pack = sih26168_find_roadpack();
    if (pack.empty()) {
        std::fprintf(stderr, "SIMULATION: missing roadpack\n");
        return 1;
    }
    if (idr_engine_init(pack.c_str(), "mock") != 1) {
        std::fprintf(stderr, "SIMULATION: init failed: %s\n", idr_engine_last_error());
        return 1;
    }
    idr_engine_set_simulation(1);
    std::printf("SIMULATION mode=%d backend=%s\n", idr_engine_is_simulation(),
                idr_engine_speed_backend());

    double t = 0.0;
    for (int i = 0; i < 400; ++i) {
        t = 0.01 * (i + 1);
        const double v = (t < 2.0) ? 5.0 * t : 10.0;
        const double lat = 12.9716 + (v * t) / 111320.0;
        if (i % 10 == 0 && t < 3.5) {
            idr_feed_gnss(t, lat, 77.5946, 920.0, v, 1.0, 10);
        }
        idr_feed_imu(t + 0.001, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    IDRNavigationOutput s = idr_get_current_state();
    std::printf("SIMULATION cruise lat=%.6f lon=%.6f speed_mps=%.3f dr=%d\n", s.lat, s.lon,
                s.speed_m_s, s.is_dead_reckoning);

    const double t0 = s.timestamp;
    for (int i = 0; i < 200; ++i) {
        idr_feed_imu(t0 + 0.01 * (i + 1), 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(250));
    s = idr_get_current_state();
    std::printf("SIMULATION outage dr=%d speed_mps=%.3f map=%s\n", s.is_dead_reckoning, s.speed_m_s,
                idr_map_status_message());

    const int accepted = idr_debug_inject_ai_speed(s.timestamp, 194.4, 0.05);
    std::printf("SIMULATION injected AI 194.4 m/s accepted=%d speed_mps=%.3f\n", accepted,
                idr_get_current_state().speed_m_s);

    idr_feed_gnss(s.timestamp + 0.2, 12.9717, 77.5946, 920.0, 8.0, 0.9, 10);
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    s = idr_get_current_state();
    std::printf("SIMULATION recovery dr=%d\n", s.is_dead_reckoning);

    if (accepted != 0 || idr_get_current_state().speed_m_s > 55.0) {
        std::fprintf(stderr, "SIMULATION: impossible speed was trusted\n");
        idr_engine_shutdown();
        return 1;
    }
    idr_engine_shutdown();
    return 0;
}
