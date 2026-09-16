#include "idr_engine_api.h"

#include <cstdio>

int main() {
    if (idr_engine_init("", "") != 1) {
        std::fprintf(stderr, "init failed: %s\n", idr_engine_last_error());
        return 1;
    }

    idr_feed_gnss(0.0, 12.9716, 77.5946, 920.0, 15.0, 1.0, 10);
    for (int i = 0; i < 50; ++i) {
        const double t = 0.01 * (i + 1);
        idr_feed_imu(t, 0.2, 0.0, 9.81, 0.0, 0.0, 0.01);
    }

    IDRNavigationOutput s = idr_get_current_state();
    std::printf("t=%.3f lat=%.6f lon=%.6f heading=%.2f speed=%.2f dr=%d conf=%.2f\n", s.timestamp,
                s.lat, s.lon, s.heading_deg, s.speed_m_s, s.is_dead_reckoning, s.confidence);

    idr_engine_shutdown();
    return 0;
}
