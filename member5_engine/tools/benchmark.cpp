#include "idr_engine_api.h"

#include <chrono>
#include <cstdio>
#include <cmath>

int main() {
    if (idr_engine_init("", "") != 1) {
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

    IDRNavigationOutput s = idr_get_current_state();
    std::printf("mean_feed_gnss_mode_switch_us=%.3f last_dr=%d\n", us, s.is_dead_reckoning);
    std::printf("target_us=10000 (handbook <10 ms GNSS deficit transition)\n");
    idr_engine_shutdown();
    return (us < 10000.0 && std::isfinite(us)) ? 0 : 1;
}
