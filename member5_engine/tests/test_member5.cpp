#include "idr_engine_api.h"
#include "member5/GnssDeficitMachine.hpp"
#include "member5/SpscRing.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <functional>
#include <thread>

#define CHECK(cond)                                                                              \
    do {                                                                                         \
        if (!(cond)) {                                                                           \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                 \
            return 1;                                                                            \
        }                                                                                        \
    } while (0)

namespace {

int test_ring() {
    sih26168::member5::SpscRing<int, 8> q;
    CHECK(!q.pop().has_value());
    for (int i = 0; i < 7; ++i) {
        CHECK(q.push(i));
    }
    CHECK(!q.push(99));
    for (int i = 0; i < 7; ++i) {
        auto v = q.pop();
        CHECK(v.has_value());
        CHECK(*v == i);
    }
    CHECK(!q.pop().has_value());
    return 0;
}

int test_deficit_machine() {
    sih26168::member5::GnssDeficitMachine sm;
    CHECK(sm.mode() == sih26168::member3::NavigationMode::DEAD_RECKONING);

    CHECK(sm.observe(1.0, 1.0, 8) == sih26168::member3::NavigationMode::GNSS_AIDED);
    CHECK(sm.evaluate(1.5) == sih26168::member3::NavigationMode::GNSS_AIDED);

    CHECK(sm.observe(2.0, 5.0, 8) == sih26168::member3::NavigationMode::DEAD_RECKONING);
    CHECK(sm.observe(3.0, 1.0, 3) == sih26168::member3::NavigationMode::DEAD_RECKONING);
    CHECK(sm.observe(4.0, 1.2, 10) == sih26168::member3::NavigationMode::GNSS_AIDED);
    CHECK(sm.evaluate(4.0 + 1.21) == sih26168::member3::NavigationMode::DEAD_RECKONING);
    return 0;
}

void wait_for(const std::function<bool()>& pred, int timeout_ms = 500) {
    const auto start = std::chrono::steady_clock::now();
    while (!pred()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
        if (std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() -
                                                                  start)
                .count() > timeout_ms) {
            break;
        }
    }
}

int test_c_abi() {
    CHECK(idr_engine_is_initialized() == 0);
    CHECK(idr_engine_init("", "") == 1);
    CHECK(idr_engine_is_initialized() == 1);

    idr_feed_gnss(10.0, 12.9716, 77.5946, 920.0, 15.0, 1.0, 10);
    wait_for([] {
        IDRNavigationOutput s = idr_get_current_state();
        return s.is_dead_reckoning == 0 && std::abs(s.lat - 12.9716) < 1e-6;
    });
    IDRNavigationOutput aided = idr_get_current_state();
    CHECK(aided.is_dead_reckoning == 0);
    CHECK(std::abs(aided.speed_m_s - 15.0) < 1e-6);

    idr_feed_gnss(11.0, 12.9716, 77.5946, 920.0, 15.0, 9.0, 10);
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 1; });
    CHECK(idr_get_current_state().is_dead_reckoning == 1);

    idr_feed_gnss(12.0, 12.98, 77.60, 920.0, 12.5, 0.8, 9);
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 0; });
    CHECK(idr_get_current_state().is_dead_reckoning == 0);

    for (int i = 0; i < 250; ++i) {
        const double t = 12.0 + 0.01 * (i + 1);
        idr_feed_imu(t, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for([] {
        IDRNavigationOutput s = idr_get_current_state();
        return s.is_dead_reckoning == 1 && s.timestamp >= 12.0 + 1.2;
    }, 1000);
    IDRNavigationOutput stale = idr_get_current_state();
    CHECK(stale.is_dead_reckoning == 1);

    idr_engine_shutdown();
    CHECK(idr_engine_is_initialized() == 0);
    IDRNavigationOutput empty = idr_get_current_state();
    CHECK(empty.timestamp == 0.0);
    return 0;
}

int test_mode_switch_latency() {
    CHECK(idr_engine_init("", "") == 1);
    idr_feed_gnss(1.0, 12.9716, 77.5946, 920.0, 10.0, 1.0, 8);
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 0; });

    const auto t0 = std::chrono::steady_clock::now();
    idr_feed_gnss(2.0, 12.9716, 77.5946, 920.0, 10.0, 8.0, 8);
    IDRNavigationOutput after = idr_get_current_state();
    const auto t1 = std::chrono::steady_clock::now();
    const double us =
        std::chrono::duration<double, std::micro>(t1 - t0).count();
    std::printf("gnss_quality_switch_latency_us=%.3f mode_dr=%d\n", us, after.is_dead_reckoning);
    CHECK(after.is_dead_reckoning == 1);
    CHECK(us < 10000.0);
    idr_engine_shutdown();
    return 0;
}

}  // namespace

int main() {
    if (test_ring() != 0) {
        return 1;
    }
    if (test_deficit_machine() != 0) {
        return 1;
    }
    if (test_c_abi() != 0) {
        return 1;
    }
    if (test_mode_switch_latency() != 0) {
        return 1;
    }
    std::printf("member5 tests passed\n");
    return 0;
}
