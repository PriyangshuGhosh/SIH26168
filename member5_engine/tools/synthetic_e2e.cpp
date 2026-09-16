#include "idr_engine_api.h"

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
constexpr double kCruiseMps = 15.0;
constexpr double kStaticEnd = 3.0;
constexpr double kAccelEnd = 9.0;
constexpr double kTunnelStart = 20.0;
constexpr double kTunnelEnd = 35.0;
constexpr double kScenarioEnd = 40.0;

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
    double lon = kLon0;
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
        s.lon = lon;
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

    if (idr_engine_init("synthetic:ns-road", "") != 1) {
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

    IDRNavigationOutput at_gnss = {};
    IDRNavigationOutput at_tunnel = {};
    IDRNavigationOutput at_reacq = {};
    double err_gnss = 0.0;
    double err_tunnel = 0.0;
    double err_reacq = 0.0;
    bool saw_dr_in_tunnel = false;
    bool gnss_mode_before_tunnel = false;
    bool gnss_mode_after = false;
    double lat_before_tunnel = kLat0;
    double lat_mid_tunnel = kLat0;

    auto sampleNear = [&](double t) -> std::pair<Truth, IDRNavigationOutput> {
        Truth tr = truth.front();
        for (const auto& s : truth) {
            if (s.t + 1e-9 >= t) {
                tr = s;
                break;
            }
        }
        /* Re-query live state is wrong after the run; use log by timestamp. */
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
    auto g18 = sampleNear(18.0);
    auto t21 = sampleNear(21.5);
    auto t30 = sampleNear(30.0);
    auto r36 = sampleNear(36.0);
    auto t19 = sampleNear(19.0);

    at_gnss = g18.second;
    at_tunnel = t30.second;
    at_reacq = r36.second;
    err_gnss = horizErrorM(g18.first.lat, g18.first.lon, g18.second.lat, g18.second.lon);
    err_tunnel = horizErrorM(t30.first.lat, t30.first.lon, t30.second.lat, t30.second.lon);
    err_reacq = horizErrorM(r36.first.lat, r36.first.lon, r36.second.lat, r36.second.lon);
    gnss_mode_before_tunnel = g18.second.is_dead_reckoning == 0;
    saw_dr_in_tunnel = t21.second.is_dead_reckoning == 1 && t30.second.is_dead_reckoning == 1;
    gnss_mode_after = r36.second.is_dead_reckoning == 0;
    lat_before_tunnel = t19.second.lat;
    lat_mid_tunnel = t30.second.lat;
    const double north_progress_m = (lat_mid_tunnel - lat_before_tunnel) * kMetersPerDegLat;

    std::vector<Check> checks;
    checks.push_back({"GNSS-aided mode before tunnel", gnss_mode_before_tunnel,
                      "dr=" + std::to_string(g18.second.is_dead_reckoning)});
    checks.push_back({"GNSS position error @18s < 25 m", err_gnss < 25.0,
                      std::to_string(err_gnss) + " m"});
    checks.push_back({"DR mode during tunnel", saw_dr_in_tunnel,
                      "dr@21.5=" + std::to_string(t21.second.is_dead_reckoning) +
                          " dr@30=" + std::to_string(t30.second.is_dead_reckoning)});
    checks.push_back({"Vehicle still advances north in DR", north_progress_m > 50.0,
                      std::to_string(north_progress_m) + " m over ~11 s"});
    checks.push_back({"DR speed stays near cruise", t30.second.speed_m_s > 8.0,
                      std::to_string(t30.second.speed_m_s) + " m/s"});
    checks.push_back({"Synthetic map snap holds longitude",
                      std::abs(t30.second.lon - kLon0) < 1e-6,
                      std::to_string(t30.second.lon)});
    checks.push_back({"DR drift @30s < 40 m after 10 s of outage", err_tunnel < 40.0,
                      std::to_string(err_tunnel) + " m"});
    checks.push_back({"GNSS-aided mode mid-cruise", g12.second.is_dead_reckoning == 0,
                      "dr=" + std::to_string(g12.second.is_dead_reckoning)});
    checks.push_back({"GNSS reacquire exits DR", gnss_mode_after,
                      "dr=" + std::to_string(r36.second.is_dead_reckoning)});
    checks.push_back({"Position error after reacquire < 25 m", err_reacq < 25.0,
                      std::to_string(err_reacq) + " m"});

    const char* csv_path = "member5_engine/tests/data/synthetic_e2e_log.csv";
    {
        std::ofstream csv(csv_path);
        if (!csv) {
            std::fprintf(stderr,
                         "cannot write %s — run from the repository root\n", csv_path);
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
    std::printf("scenario: 3s static, 6s accel to 15 m/s, cruise, tunnel 20-35s, GNSS back\n");
    std::printf("stand-ins: mock speed integrator (M1), stub EKF (M3), synthetic NS road (M4)\n");
    std::printf("real: Member 2 FrameAligner + GNSS deficit SM + C ABI\n");
    std::printf("t=18s  lat=%.6f lon=%.6f speed=%.2f dr=%d err=%.2f m\n", at_gnss.lat, at_gnss.lon,
                at_gnss.speed_m_s, at_gnss.is_dead_reckoning, err_gnss);
    std::printf("t=30s  lat=%.6f lon=%.6f speed=%.2f dr=%d err=%.2f m (tunnel)\n", at_tunnel.lat,
                at_tunnel.lon, at_tunnel.speed_m_s, at_tunnel.is_dead_reckoning, err_tunnel);
    std::printf("t=36s  lat=%.6f lon=%.6f speed=%.2f dr=%d err=%.2f m (reacquire)\n", at_reacq.lat,
                at_reacq.lon, at_reacq.speed_m_s, at_reacq.is_dead_reckoning, err_reacq);
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
    std::printf("RESULT: PASS — Member 5 pipeline holds a synthetic intact stack\n");
    return 0;
}
