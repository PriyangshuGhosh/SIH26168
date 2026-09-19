#include "idr_engine_api.h"
#include "member2/FrameAligner.hpp"
#include "member3/EKFFusionEngine.hpp"
#include "member4/MapMatchingEngine.hpp"
#include "member5/GnssDeficitMachine.hpp"
#include "member5/SpscRing.hpp"
#include "member5/ImuTimestampPairer.hpp"
#include "member5/MapCatalog.hpp"
#include "member5/SpeedUnits.hpp"
#include "member5/SpeedValidity.hpp"
#include "test_support.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <functional>
#include <limits>
#include <string>
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

void wait_for(const std::function<bool()>& pred, int timeout_ms = 800) {
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

int test_production_errors() {
    CHECK(idr_engine_is_initialized() == 0);
    CHECK(idr_engine_init("", "") == 0);
    CHECK(idr_engine_is_initialized() == 0);
    CHECK(std::string(idr_engine_last_error()).find("map") != std::string::npos);

    CHECK(idr_engine_init("mock:ns-road", "mock") == 0);

    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "") == 0);
    {
        const std::string err = idr_engine_last_error();
        CHECK(err.find("ONNX") != std::string::npos || err.find("onnx") != std::string::npos ||
              err.find("mock") != std::string::npos);
    }

    CHECK(idr_engine_init(pack.c_str(), "/no/such/speed_estimator.onnx") == 0);

    {
        const char* bogus = "/tmp/sih26168_not_a_map.roadpack";
        std::ofstream out(bogus);
        out << "not a roadpack\n";
        out.close();
        CHECK(idr_engine_init(bogus, "mock") == 0);
        CHECK(std::string(idr_engine_last_error()).size() > 0);
    }

    CHECK(idr_engine_init("member4_map_matching/data/small_road_network.graphml", "mock") == 0);
    CHECK(std::string(idr_engine_last_error()).find("roadpack") != std::string::npos);
    return 0;
}

int test_c_abi() {
    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "mock") == 1);
    CHECK(idr_engine_is_initialized() == 1);
    CHECK(std::string(idr_engine_speed_backend()).find("mock") != std::string::npos);

    idr_feed_gnss(10.0, 12.9716, 77.5946, 920.0, 15.0, 1.0, 10);
    wait_for([] {
        IDRNavigationOutput s = idr_get_current_state();
        return s.is_dead_reckoning == 0 && std::abs(s.lat - 12.9716) < 1e-3;
    });
    IDRNavigationOutput aided = idr_get_current_state();
    CHECK(aided.is_dead_reckoning == 0);
    CHECK(std::abs(aided.speed_m_s - 15.0) < 2.0);

    idr_feed_gnss(11.0, 12.9716, 77.5946, 920.0, 15.0, 9.0, 10);
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 1; });
    CHECK(idr_get_current_state().is_dead_reckoning == 1);

    idr_feed_gnss(12.0, 12.9718, 77.5946, 920.0, 12.5, 0.8, 9);
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 0; });
    CHECK(idr_get_current_state().is_dead_reckoning == 0);

    for (int i = 0; i < 250; ++i) {
        const double t = 12.0 + 0.01 * (i + 1);
        idr_feed_imu(t, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for(
        [] {
            IDRNavigationOutput s = idr_get_current_state();
            return s.is_dead_reckoning == 1 && s.timestamp >= 12.0 + 1.2;
        },
        1500);
    IDRNavigationOutput stale = idr_get_current_state();
    CHECK(stale.is_dead_reckoning == 1);

    idr_engine_shutdown();
    CHECK(idr_engine_is_initialized() == 0);
    IDRNavigationOutput empty = idr_get_current_state();
    CHECK(empty.timestamp == 0.0);
    CHECK(idr_get_road_segment_id() == 0);
    return 0;
}

int test_mode_switch_latency() {
    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "mock") == 1);
    idr_feed_gnss(1.0, 12.9716, 77.5946, 920.0, 10.0, 1.0, 8);
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 0; });

    const auto t0 = std::chrono::steady_clock::now();
    idr_feed_gnss(2.0, 12.9716, 77.5946, 920.0, 10.0, 8.0, 8);
    IDRNavigationOutput after = idr_get_current_state();
    const auto t1 = std::chrono::steady_clock::now();
    const double us = std::chrono::duration<double, std::micro>(t1 - t0).count();
    std::printf("gnss_quality_switch_latency_us=%.3f mode_dr=%d\n", us, after.is_dead_reckoning);
    CHECK(after.is_dead_reckoning == 1);
    CHECK(us < 10000.0);
    idr_engine_shutdown();
    return 0;
}

int test_malformed_and_ooo() {
    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "mock") == 1);
    idr_feed_gnss(1.0, 12.9716, 77.5946, 920.0, 5.0, 1.0, 8);
    idr_feed_imu(1.10, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    idr_feed_imu(1.05, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0); /* OOO: aligner INVALID, skipped */
    idr_feed_imu(1.20, std::nan(""), 0.0, 9.81, 0.0, 0.0, 0.0);
    idr_feed_imu(1.30, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    wait_for([] { return idr_get_current_state().timestamp >= 1.29; }, 800);
    CHECK(std::isfinite(idr_get_current_state().lat));
    idr_engine_shutdown();
    return 0;
}

int test_real_map_matcher_not_stub() {
    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "mock") == 1);

    sih26168::member4::MapMatchingEngine direct;
    CHECK(direct.loadRoadpack(pack));
    sih26168::member3::NavigationState nav;
    nav.timestamp = 5.0;
    nav.latitude = 12.9716;
    nav.longitude = 77.5946;
    nav.yaw_rad = 0.0;
    nav.position_cov_m2[0][0] = 4.0;
    nav.position_cov_m2[1][1] = 4.0;
    const auto expected = direct.match(nav);

    /* Drive north along the synthetic grid origin (a real vertical segment). */
    for (int i = 0; i < 80; ++i) {
        const double t = 0.01 * (i + 1);
        const double lat = 12.9716 + (0.4 * t) / 111320.0;
        idr_feed_gnss(t, lat, 77.5946, 920.0, 8.0, 1.0, 10);
        idr_feed_imu(t + 0.001, 0.3, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for([] { return idr_get_road_segment_id() != 0 || idr_is_on_road_network() == 1; }, 2000);

    const long long seg = idr_get_road_segment_id();
    /* StubMapMatcher used 123456789 / 424242. Real roadpack ids are small sequential. */
    CHECK(seg != 123456789);
    CHECK(seg != 424242);
    if (expected.road_segment_id != 0) {
        CHECK(seg != 0);
    }
    CHECK(std::string(idr_engine_speed_backend()) != "stub");
    idr_engine_shutdown();
    return 0;
}

int test_m2_m3_contract() {
    sih26168::member2::FrameAligner aligner;
    sih26168::member3::EKFFusionEngine ekf;
    for (int i = 0; i < 120; ++i) {
        const double t = 0.01 * i;
        auto f = aligner.process(t, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0);
        if (f.status != sih26168::member2::CalibrationStatus::INVALID) {
            ekf.predict(f, sih26168::member3::NavigationMode::DEAD_RECKONING);
        }
    }
    CHECK(std::isfinite(ekf.state().v_x));
    CHECK(std::isfinite(ekf.state().yaw_rad));
    return 0;
}

int test_gnss_dropout_recovery() {
    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "mock") == 1);

    /* PHASE A: GNSS available + IMU */
    for (int i = 0; i < 250; ++i) {
        const double t = 0.01 * (i + 1);
        if (i % 100 == 0) {
            idr_feed_gnss(t, 12.9716 + (8.0 * t) / 111320.0, 77.5946, 920.0, 8.0, 1.0, 9);
        }
        idr_feed_imu(t, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 0; }, 1500);
    CHECK(idr_get_current_state().is_dead_reckoning == 0);
    const double lat_a = idr_get_current_state().lat;
    CHECK(std::isfinite(lat_a));

    /* PHASE B: GNSS dropout — IMU only for > 1.2 s */
    const double t_b0 = 2.50;
    for (int i = 0; i < 200; ++i) {
        const double t = t_b0 + 0.01 * (i + 1);
        idr_feed_imu(t, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for(
        [] {
            IDRNavigationOutput s = idr_get_current_state();
            return s.is_dead_reckoning == 1 && s.timestamp >= 2.50 + 1.2;
        },
        1500);
    IDRNavigationOutput dr = idr_get_current_state();
    CHECK(dr.is_dead_reckoning == 1);
    CHECK(std::isfinite(dr.lat) && std::isfinite(dr.lon));
    CHECK(dr.timestamp > t_b0);

    /* PHASE C: GNSS recovery */
    const double t_c = dr.timestamp + 0.05;
    idr_feed_gnss(t_c, 12.9718, 77.5946, 920.0, 7.5, 0.9, 10);
    for (int i = 0; i < 50; ++i) {
        idr_feed_imu(t_c + 0.01 * (i + 1), 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 0; }, 1500);
    CHECK(idr_get_current_state().is_dead_reckoning == 0);
    CHECK(std::isfinite(idr_get_current_state().lat));

    idr_engine_shutdown();
    return 0;
}

int test_onnx_path() {
#if defined(IDR_WITH_ONNXRUNTIME)
    const std::string pack = sih26168_find_roadpack();
    const char* dummy = "member5_engine/tests/data/dummy_speed_estimator.onnx";
    std::ifstream in(dummy, std::ios::binary);
    if (!in.good()) {
        std::printf("onnx dummy model missing; skip load/infer wiring test\n");
        return 0;
    }
    in.close();
    CHECK(idr_engine_init(pack.c_str(), dummy) == 1);
    CHECK(std::string(idr_engine_speed_backend()).find("onnx") != std::string::npos);
    for (int i = 0; i < 250; ++i) {
        const double t = 0.01 * i;
        idr_feed_imu(t, 0.2, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for([] { return idr_get_current_state().timestamp >= 2.4; }, 1500);
    CHECK(std::isfinite(idr_get_current_state().speed_m_s));
    idr_engine_shutdown();

    CHECK(idr_engine_init(pack.c_str(), "member5_engine/tests/data/not_a_map.roadpack") == 0);
#else
    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "member5_engine/tests/data/dummy_speed_estimator.onnx") == 0);
    CHECK(std::string(idr_engine_last_error()).find("ONNX") != std::string::npos);
#endif
    return 0;
}

/* Regression: a GNSS fix without speed (Android hasSpeed()==false -> NaN) must not reach the EKF
   as an artificial 0 m/s measurement. A real 0.0 m/s must still be a valid measurement. */
int test_gnss_without_speed_is_not_zero_measurement() {
    using sih26168::member3::EKFFusionEngine;
    using sih26168::member3::NavigationMode;
    using sih26168::member5::GnssSample;
    using sih26168::member5::toGnssMeasurement;
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double lat = 12.9716;
    const double lon = 77.5946;

    CHECK(!toGnssMeasurement(GnssSample{0.0, lat, lon, 900.0, nan, 1.0, 10}).speed_valid);
    CHECK(toGnssMeasurement(GnssSample{0.0, lat, lon, 900.0, 0.0, 1.0, 10}).speed_valid);
    CHECK(toGnssMeasurement(GnssSample{0.0, lat, lon, 900.0, 1.5, 1.0, 10}).speed_valid);

    /* Establish ~1.3 m/s with real speed fixes, then apply a same-position fix at t=0.3 that either
       has no speed (NaN) or a real 0.0 m/s; only the latter may pull the velocity down. */
    auto speed_after = [&](double third_fix_speed, bool position_only, bool* accepted) {
        EKFFusionEngine ekf;
        sih26168::member2::AlignedIMUFrame f{};
        f.az_v = 9.80665;
        f.status = sih26168::member2::CalibrationStatus::FULLY_ALIGNED;
        ekf.updateGnss(toGnssMeasurement(GnssSample{0.0, lat, lon, 900.0, 1.5, 1.0, 10}));
        for (int i = 1; i <= 2; ++i) {
            f.timestamp = 0.1 * i;
            ekf.predict(f, NavigationMode::GNSS_AIDED);
            ekf.updateGnss(toGnssMeasurement(GnssSample{0.1 * i, lat, lon, 900.0, 1.5, 1.0, 10}));
        }
        f.timestamp = 0.3;
        ekf.predict(f, NavigationMode::GNSS_AIDED);
        const double before = ekf.state().v_x;
        auto m = toGnssMeasurement(GnssSample{0.3, lat, lon, 900.0, third_fix_speed, 1.0, 10});
        if (position_only) {
            m.speed_valid = false; /* Member 3's explicit position-only convention */
        }
        ekf.updateGnss(m);
        if (accepted != nullptr) {
            *accepted = ekf.state().last_gnss_accepted;
        }
        return std::make_pair(before, ekf.state().v_x);
    };

    bool none_accepted = false;
    const auto none = speed_after(nan, false, &none_accepted);
    const auto position_only = speed_after(1.5, true, nullptr);
    const auto zero = speed_after(0.0, false, nullptr);
    CHECK(none.first > 0.5);
    CHECK(none_accepted);
    CHECK(std::abs(none.second - position_only.second) < 1e-12);
    CHECK(zero.second < none.second - 0.2);
    return 0;
}

int test_speed_validity_matrix() {
    using sih26168::member5::SpeedValidityFilter;
    using sih26168::member5::SpeedRejectReason;
    using sih26168::member5::mpsToKmh;
    using sih26168::member5::kmhToMps;

    CHECK(std::abs(mpsToKmh(10.0) - 36.0) < 1e-12);
    CHECK(std::abs(kmhToMps(36.0) - 10.0) < 1e-12);
    CHECK(std::abs(mpsToKmh(194.4) - 699.84) < 0.01);

    SpeedValidityFilter f;
    SpeedRejectReason why = SpeedRejectReason::None;

    CHECK(f.accept(0.0, 0.0, &why)); /* 1. 0 km/h stationary */
    CHECK(f.accept(1.0, kmhToMps(1.0), &why));
    CHECK(f.accept(4.0, kmhToMps(10.0), &why));
    CHECK(f.accept(8.0, kmhToMps(50.0), &why));
    CHECK(f.accept(14.0, kmhToMps(100.0), &why)); /* 5. 100 km/h */

    /* 6-7 braking / acceleration at realistic dt */
    CHECK(f.accept(16.0, kmhToMps(60.0), &why));
    CHECK(f.accept(18.0, kmhToMps(80.0), &why));

    const double trusted = f.lastTrustedMps();
    CHECK(!f.accept(18.05, 194.4, &why)); /* 8. isolated 700 km/h */
    CHECK(why == SpeedRejectReason::AboveMax || why == SpeedRejectReason::ImpossibleJump);
    CHECK(std::abs(f.lastTrustedMps() - trusted) < 1e-12);

    CHECK(!f.accept(18.10, 194.4, &why)); /* 9. repeated spike */
    CHECK(!f.accept(19.0, std::nan(""), &why)); /* 10. NaN */
    CHECK(!f.accept(20.0, std::numeric_limits<double>::infinity(), &why)); /* 11. Inf */
    CHECK(!f.accept(21.0, -1.0, &why)); /* 12. negative */

    CHECK(!f.acceptAiMeasurement(22.0, 10.0, 0.0, &why)); /* 13. zero variance */
    CHECK(why == SpeedRejectReason::VarianceInvalid);
    CHECK(!f.acceptAiMeasurement(22.0, 10.0, 1e-18, &why)); /* 14. tiny variance */
    CHECK(f.acceptAiMeasurement(24.0, kmhToMps(90.0), 400.0, &why)); /* 15. huge but usable variance */

    CHECK(!f.accept(10.0, 5.0, &why)); /* 17. timestamp regression */
    CHECK(why == SpeedRejectReason::TimestampInvalid);

    SpeedValidityFilter g;
    CHECK(g.accept(0.0, 2.0, &why));
    CHECK(!g.accept(0.05, 194.4, &why)); /* jump using actual dt */
    CHECK(g.lastTrustedMps() < 5.0);

    SpeedValidityFilter stat;
    CHECK(stat.accept(0.0, 0.0, &why));
    CHECK(stat.accept(0.02, 0.05, &why)); /* 19. tiny phone movement */
    CHECK(stat.lastTrustedMps() < 1.0);
    CHECK(stat.accept(1.0, 0.2, &why)); /* 20. engine vibration-scale */
    CHECK(stat.lastTrustedMps() < 1.0);
    return 0;
}

int test_imu_timestamp_pairer() {
    sih26168::member5::ImuTimestampPairer p(0.008);
    CHECK(std::abs(sih26168::member5::sensorEventNsToSeconds(1'000'000'000LL) - 1.0) < 1e-12);
    auto none = p.feedAccel(1.000, 0.1, 0.0, 9.81);
    CHECK(!none.has_value());
    auto paired = p.feedGyro(1.003, 0.0, 0.0, 0.01);
    CHECK(paired.has_value());
    CHECK(std::abs(paired->ax - 0.1) < 1e-12);
    CHECK(std::abs(paired->gz - 0.01) < 1e-12);
    auto stale = p.feedGyro(1.050, 0.0, 0.0, 0.0); /* 47 ms skew vs last accel */
    CHECK(!stale.has_value());
    auto dup = p.feedAccel(1.002, 0.2, 0.0, 9.81);
    CHECK(!dup.has_value()); /* timestamp regression vs last emit */
    return 0;
}

int test_map_catalog_and_out_of_region() {
    const std::string pack = sih26168_find_roadpack();
    sih26168::member5::MapCatalog cat;
    CHECK(cat.loadManifestFile("member4_map_matching/data/maps/manifest.json"));
    CHECK(cat.findCovering(12.9716, 77.5946) != nullptr);
    CHECK(cat.findCovering(28.6139, 77.2090) == nullptr); /* Delhi */

    CHECK(idr_engine_init(pack.c_str(), "mock") == 1);
    CHECK(idr_select_map_for_location(12.9716, 77.5946) == 1);
    CHECK(idr_map_covers_location(12.9716, 77.5946) == 1);
    CHECK(idr_select_map_for_location(28.6139, 77.2090) == 0);
    CHECK(std::string(idr_map_status_message()).find("NOT AVAILABLE") != std::string::npos);

    idr_feed_gnss(1.0, 28.6139, 77.2090, 200.0, 5.0, 1.0, 10);
    wait_for([] { return idr_get_current_state().timestamp >= 1.0; }, 800);
    CHECK(idr_is_on_road_network() == 0);
    IDRNavigationOutput far = idr_get_current_state();
    CHECK(std::abs(far.lat - 28.6139) < 0.01);
    CHECK(std::abs(far.lon - 77.2090) < 0.01);

    CHECK(idr_engine_init("member4_map_matching/data/maps/manifest.json", "mock") == 1);
    CHECK(idr_select_map_for_location(12.9720, 77.5950) == 1);
    CHECK(idr_select_map_for_location(17.6868, 83.2185) == 0); /* Vizag vs provisioned grid */
    idr_engine_shutdown();
    return 0;
}

int test_e2e_speed_spike_and_gnss_outage_map() {
    const std::string pack = sih26168_find_roadpack();
    CHECK(idr_engine_init(pack.c_str(), "mock") == 1);
    CHECK(idr_select_map_for_location(12.9716, 77.5946) == 1);

    /* START 0, ACCEL, CRUISE, BRAKE via GNSS+IMU (canonical m/s). */
    struct Phase {
        double t0;
        double speed;
        int n;
    };
    const Phase phases[] = {{0.0, 0.0, 50}, {0.5, 5.0, 50}, {1.0, 10.0, 80}, {1.8, 0.0, 50}};
    double t = 0.0;
    for (const auto& ph : phases) {
        for (int i = 0; i < ph.n; ++i) {
            t = ph.t0 + 0.01 * (i + 1);
            idr_feed_gnss(t, 12.9716 + (ph.speed * t) / 111320.0, 77.5946, 920.0, ph.speed, 1.0, 10);
            idr_feed_imu(t + 0.001, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
        }
    }
    wait_for([] { return idr_get_current_state().timestamp > 2.0; }, 1500);
    IDRNavigationOutput cruise = idr_get_current_state();
    CHECK(cruise.speed_m_s < 55.0);
    CHECK(std::abs(sih26168::member5::mpsToKmh(cruise.speed_m_s) - 700.0) > 100.0);

    /* Gravity-leak / tiny-phone-motion: large ax, timestamps in seconds. */
    for (int i = 0; i < 2000; ++i) {
        t += 0.01;
        idr_feed_imu(t, 9.81, 0.0, 0.2, 0.0, 0.0, 0.0);
    }
    wait_for([t] { return idr_get_current_state().timestamp >= t - 0.05; }, 2000);
    IDRNavigationOutput after = idr_get_current_state();
    CHECK(after.speed_m_s <= 55.0 + 1e-6);
    CHECK(sih26168::member5::mpsToKmh(after.speed_m_s) < 250.0);
    IDRDiagnostics diag = idr_get_diagnostics();
    CHECK(diag.ekf_speed_mps <= 55.0 + 1e-6);

    /* GNSS outage: keep using already-loaded map; no network. */
    const double lat_before = after.lat;
    const double t0 = after.timestamp;
    for (int i = 0; i < 200; ++i) {
        idr_feed_imu(t0 + 0.01 * (i + 1), 0.0, 0.0, 9.81, 0.0, 0.0, 0.0);
    }
    wait_for(
        [t0] {
            IDRNavigationOutput s = idr_get_current_state();
            return s.is_dead_reckoning == 1 && s.timestamp >= t0 + 1.2;
        },
        1500);
    IDRNavigationOutput dr = idr_get_current_state();
    CHECK(dr.is_dead_reckoning == 1);
    CHECK(std::abs(dr.lat - 28.6) > 1.0); /* not teleported to Delhi */
    CHECK(std::abs(dr.lat - lat_before) < 0.05);

    idr_feed_gnss(dr.timestamp + 0.05, 12.9717, 77.5946, 920.0, 5.0, 0.9, 10);
    wait_for([] { return idr_get_current_state().is_dead_reckoning == 0; }, 1500);
    CHECK(idr_get_current_state().is_dead_reckoning == 0);
    idr_engine_shutdown();
    return 0;
}

}  // namespace

int main() {
#if defined(__has_include)
#if __has_include("member5/StubMapMatcher.hpp")
#error "StubMapMatcher.hpp must not exist on the production include path"
#endif
#if __has_include("member5/StubFusionEngine.hpp")
#error "StubFusionEngine.hpp must not exist on the production include path"
#endif
#endif

    if (test_ring() != 0) {
        return 1;
    }
    if (test_deficit_machine() != 0) {
        return 1;
    }
    if (test_production_errors() != 0) {
        return 1;
    }
    if (test_c_abi() != 0) {
        return 1;
    }
    if (test_mode_switch_latency() != 0) {
        return 1;
    }
    if (test_malformed_and_ooo() != 0) {
        return 1;
    }
    if (test_real_map_matcher_not_stub() != 0) {
        return 1;
    }
    if (test_m2_m3_contract() != 0) {
        return 1;
    }
    if (test_gnss_dropout_recovery() != 0) {
        return 1;
    }
    if (test_onnx_path() != 0) {
        return 1;
    }
    if (test_gnss_without_speed_is_not_zero_measurement() != 0) {
        return 1;
    }
    if (test_speed_validity_matrix() != 0) {
        return 1;
    }
    if (test_imu_timestamp_pairer() != 0) {
        return 1;
    }
    if (test_map_catalog_and_out_of_region() != 0) {
        return 1;
    }
    if (test_e2e_speed_spike_and_gnss_outage_map() != 0) {
        return 1;
    }
    std::printf("member5 tests passed\n");
    return 0;
}
