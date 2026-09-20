#include "idr_engine_api.h"
#include "test_support.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

constexpr double kPi = 3.14159265358979323846;
constexpr double kG = 9.80665;
constexpr double kDt = 0.01;
constexpr double kLat0 = 12.9716;
constexpr double kLon0 = 77.5946;
constexpr double kAlt = 920.0;
constexpr double kMetersPerDegLat = 111320.0;
constexpr double kCruiseMps = 8.0;
constexpr double kStaticEnd = 3.0;
constexpr double kAccelEnd = 7.0;
constexpr double kTunnelStart = 16.0;
constexpr double kTunnelEnd = 24.0;
constexpr double kScenarioEnd = 30.0;

double metersPerDegLon(double lat_deg) {
    return kMetersPerDegLat * std::cos(lat_deg * kPi / 180.0);
}

double horizErrorM(double lat_a, double lon_a, double lat_b, double lon_b) {
    const double mid = 0.5 * (lat_a + lat_b);
    const double dn = (lat_a - lat_b) * kMetersPerDegLat;
    const double de = (lon_a - lon_b) * metersPerDegLon(mid);
    return std::sqrt(dn * dn + de * de);
}

struct Truth {
    double t{0.0};
    double lat{kLat0};
    double lon{kLon0};
    double speed{0.0};
    double ax{0.0};
    int gnss_ok{0};
};

double accelAt(double t) {
    if (t < kStaticEnd) {
        return 0.0;
    }
    if (t < kAccelEnd) {
        return kCruiseMps / (kAccelEnd - kStaticEnd);
    }
    return 0.0;
}

double speedAt(double t) {
    if (t <= kStaticEnd) {
        return 0.0;
    }
    if (t < kAccelEnd) {
        return accelAt(t) * (t - kStaticEnd);
    }
    return kCruiseMps;
}

bool gnssHealthy(double t) { return t + 1e-9 < kTunnelStart || t + 1e-9 >= kTunnelEnd; }

void integrateTruth(std::vector<Truth>& samples) {
    const int n = static_cast<int>(kScenarioEnd / kDt) + 1;
    samples.resize(static_cast<std::size_t>(n));
    double lat = kLat0;
    for (int i = 0; i < n; ++i) {
        const double t = i * kDt;
        const double v = speedAt(t);
        const double ax = accelAt(t);
        if (i > 0) {
            lat += (v * kDt) / kMetersPerDegLat;
        }
        Truth s;
        s.t = t;
        s.lat = lat;
        s.lon = kLon0;
        s.speed = v;
        s.ax = ax;
        s.gnss_ok = gnssHealthy(t) ? 1 : 0;
        samples[static_cast<std::size_t>(i)] = s;
    }
}

bool waitForTime(double t, int timeout_ms) {
    const auto start = std::chrono::steady_clock::now();
    while (idr_get_current_state().timestamp + 1e-4 < t) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                                 std::chrono::steady_clock::now() - start)
                                 .count();
        if (elapsed > timeout_ms) {
            return false;
        }
    }
    return true;
}

struct Check {
    const char* name;
    bool ok;
    std::string detail;
};

}  // namespace

int main() {
    std::vector<Truth> truth;
    integrateTruth(truth);

    const std::string pack = sih26168_find_roadpack();
    if (idr_engine_init(pack.c_str(), "mock") != 1) {
        std::fprintf(stderr, "init failed: %s\n", idr_engine_last_error());
        return 1;
    }

    int last_gnss_sec = -1;
    std::vector<IDRNavigationOutput> log;
    log.reserve(truth.size() / 10);

    for (std::size_t i = 0; i < truth.size(); ++i) {
        const Truth& s = truth[i];
        const double az = kG;
        idr_feed_imu(s.t, s.ax, 0.0, az, 0.0, 0.0, 0.0);

        const int sec = static_cast<int>(std::floor(s.t + 1e-9));
        if (s.gnss_ok && sec != last_gnss_sec && std::abs(s.t - sec) < kDt * 0.5) {
            idr_feed_gnss(s.t, s.lat, s.lon, kAlt, s.speed, 1.1, 9);
            last_gnss_sec = sec;
        }

        if (i % 25 == 0 || i + 1 == truth.size()) {
            if (!waitForTime(s.t, 2000)) {
                std::fprintf(stderr, "timeout waiting for t=%.3f (state t=%.3f)\n", s.t,
                             idr_get_current_state().timestamp);
                idr_engine_shutdown();
                return 1;
            }
        }

        if (i % 10 == 0) {
            log.push_back(idr_get_current_state());
        }
    }

    if (!waitForTime(kScenarioEnd - kDt, 2000)) {
        std::fprintf(stderr, "final drain timeout\n");
        idr_engine_shutdown();
        return 1;
    }

    auto sampleNear = [&](double t) -> std::pair<Truth, IDRNavigationOutput> {
        Truth tr = truth.front();
        for (const auto& s : truth) {
            if (s.t + 1e-9 >= t) {
                tr = s;
                break;
            }
        }
        IDRNavigationOutput best = log.empty() ? IDRNavigationOutput{} : log.front();
        double best_dt = 1e9;
        for (const auto& o : log) {
            const double d = std::abs(o.timestamp - t);
            if (d < best_dt) {
                best_dt = d;
                best = o;
            }
        }
        return {tr, best};
    };

    auto g12 = sampleNear(12.0);
    auto g14 = sampleNear(14.0);
    auto t17 = sampleNear(17.5);
    auto t22 = sampleNear(22.0);
    auto r26 = sampleNear(26.0);
    auto t15 = sampleNear(15.0);

    const double err_gnss = horizErrorM(g14.first.lat, g14.first.lon, g14.second.lat, g14.second.lon);
    const double err_tunnel = horizErrorM(t22.first.lat, t22.first.lon, t22.second.lat, t22.second.lon);
    const double err_reacq = horizErrorM(r26.first.lat, r26.first.lon, r26.second.lat, r26.second.lon);
    const bool gnss_mode_before_tunnel = g14.second.is_dead_reckoning == 0;
    const bool saw_dr_in_tunnel = t17.second.is_dead_reckoning == 1 && t22.second.is_dead_reckoning == 1;
    const bool gnss_mode_after = r26.second.is_dead_reckoning == 0;
    const double north_progress_m = (t22.second.lat - t15.second.lat) * kMetersPerDegLat;
    const long long seg = idr_get_road_segment_id();
    const int on_road = idr_is_on_road_network();

    std::vector<Check> checks;
    checks.push_back({"GNSS-aided mode before tunnel", gnss_mode_before_tunnel,
                      "dr=" + std::to_string(g14.second.is_dead_reckoning)});
    checks.push_back({"GNSS position error @14s < 40 m", err_gnss < 40.0,
                      std::to_string(err_gnss) + " m"});
    checks.push_back({"DR mode during tunnel", saw_dr_in_tunnel,
                      "dr@17.5=" + std::to_string(t17.second.is_dead_reckoning) +
                          " dr@22=" + std::to_string(t22.second.is_dead_reckoning)});
    checks.push_back({"Vehicle still advances north in DR", north_progress_m > 20.0,
                      std::to_string(north_progress_m) + " m"});
    checks.push_back({"DR speed stays positive", t22.second.speed_m_s > 1.0,
                      std::to_string(t22.second.speed_m_s) + " m/s"});
    checks.push_back({"Matched longitude near NS grid",
                      std::abs(t22.second.lon - kLon0) < 5e-4,
                      std::to_string(t22.second.lon)});
    checks.push_back({"DR drift @22s < 80 m after ~6 s outage", err_tunnel < 80.0,
                      std::to_string(err_tunnel) + " m"});
    checks.push_back({"GNSS-aided mode mid-cruise", g12.second.is_dead_reckoning == 0,
                      "dr=" + std::to_string(g12.second.is_dead_reckoning)});
    checks.push_back({"GNSS reacquire exits DR", gnss_mode_after,
                      "dr=" + std::to_string(r26.second.is_dead_reckoning)});
    checks.push_back({"Position error after reacquire < 40 m", err_reacq < 40.0,
                      std::to_string(err_reacq) + " m"});
    checks.push_back({"Not StubMapMatcher magic segment id",
                      seg != 123456789 && seg != 424242,
                      std::to_string(seg)});
    checks.push_back({"Explicit mock speed backend",
                      std::string(idr_engine_speed_backend()).find("mock") != std::string::npos,
                      idr_engine_speed_backend()});

    const char* csv_path = "member5_engine/tests/data/synthetic_e2e_log.csv";
    {
        std::ofstream csv(csv_path);
        if (!csv) {
            std::fprintf(stderr, "cannot write %s � run from the repository root\n", csv_path);
            idr_engine_shutdown();
            return 1;
        }
        csv << "t,gt_lat,gt_lon,gt_speed,est_lat,est_lon,est_speed,dr,confidence,err_m\n";
        for (const auto& o : log) {
            Truth tr = truth.front();
            for (const auto& s : truth) {
                if (s.t + 1e-9 >= o.timestamp) {
                    tr = s;
                    break;
                }
            }
            const double err = horizErrorM(tr.lat, tr.lon, o.lat, o.lon);
            csv << o.timestamp << "," << tr.lat << "," << tr.lon << "," << tr.speed << "," << o.lat
                << "," << o.lon << "," << o.speed_m_s << "," << o.is_dead_reckoning << ","
                << o.confidence << "," << err << "\n";
        }
    }

    std::printf("=== Member 5 synthetic end-to-end ===\n");
    std::printf("scenario: 3s static, accel to 8 m/s, cruise, tunnel 16-24s, GNSS back (30s)\n");
    std::printf("modules: M2 FrameAligner, M1 explicit mock, M3 EKF, M4 MapMatchingEngine (.roadpack)\n");
    std::printf("map: %s backend=%s segment=%lld on_road=%d\n", pack.c_str(),
                idr_engine_speed_backend(), seg, on_road);
    std::printf("t=14s  lat=%.6f lon=%.6f speed=%.2f dr=%d err=%.2f m\n", g14.second.lat,
                g14.second.lon, g14.second.speed_m_s, g14.second.is_dead_reckoning, err_gnss);
    std::printf("t=22s  lat=%.6f lon=%.6f speed=%.2f dr=%d err=%.2f m (tunnel)\n", t22.second.lat,
                t22.second.lon, t22.second.speed_m_s, t22.second.is_dead_reckoning, err_tunnel);
    std::printf("t=26s  lat=%.6f lon=%.6f speed=%.2f dr=%d err=%.2f m (reacquire)\n", r26.second.lat,
                r26.second.lon, r26.second.speed_m_s, r26.second.is_dead_reckoning, err_reacq);
    std::printf("log: %s (%zu rows)\n", csv_path, log.size());

    int failed = 0;
    for (const auto& c : checks) {
        std::printf("[%s] %s (%s)\n", c.ok ? "PASS" : "FAIL", c.name, c.detail.c_str());
        if (!c.ok) {
            ++failed;
        }
    }

    idr_engine_shutdown();
    if (failed != 0) {
        std::printf("RESULT: FAIL (%d checks)\n", failed);
        return 1;
    }
    std::printf("RESULT: PASS � pipeline uses real M2/M3/M4 with explicit mock M1\n");
    return 0;
}
