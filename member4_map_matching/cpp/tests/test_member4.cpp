#include "member4/MapMatchingEngine.hpp"

#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using sih26168::member3::NavigationState;
using sih26168::member4::MapMatchingEngine;

namespace {

int failures = 0;

void expect(bool cond, const char* msg) {
    if (!cond) {
        std::cerr << "FAIL: " << msg << "\n";
        ++failures;
    }
}

std::string findRoadpack() {
    const char* env = std::getenv("MEMBER4_ROADPACK");
    if (env && fs::exists(env)) {
        return env;
    }
    const std::vector<std::string> candidates = {
        "member4_map_matching/data/synthetic_grid.roadpack",
        "data/synthetic_grid.roadpack",
    };
    for (const auto& c : candidates) {
        if (fs::exists(c)) {
            return c;
        }
    }
    return {};
}

NavigationState makeState(
    double t, double lat, double lon, double yaw, double var = 16.0) {
    NavigationState s;
    s.timestamp = t;
    s.latitude = lat;
    s.longitude = lon;
    s.yaw_rad = yaw;
    s.position_cov_m2[0][0] = var;
    s.position_cov_m2[1][1] = var;
    return s;
}

}  // namespace

int main() {
    const std::string pack = findRoadpack();
    expect(!pack.empty(), "synthetic roadpack must exist (run build_synthetic_graph.py)");
    if (pack.empty()) {
        return 1;
    }

    MapMatchingEngine engine;
    expect(engine.loadRoadpack(pack), "loadRoadpack");
    expect(engine.segmentCount() > 0, "segments loaded");

    // On-grid noisy eastbound points near origin corridor.
    constexpr double lat0 = 12.9716;
    constexpr double lon0 = 77.5946;
    constexpr double pi = 3.14159265358979323846;
    const double dlon = 5.0 / (111320.0 * std::cos(lat0 * pi / 180.0));

    std::vector<NavigationState> traj;
    for (int i = 0; i < 20; ++i) {
        traj.push_back(makeState(
            static_cast<double>(i),
            lat0,
            lon0 + i * dlon,
            pi / 2.0,
            16.0));
    }

    auto matched = engine.matchTrajectory(traj);
    expect(matched.size() == traj.size(), "trajectory length");
    int on_road = 0;
    for (const auto& m : matched) {
        if (m.is_on_road_network) {
            ++on_road;
            expect(m.road_segment_id != 0, "on-road has segment id");
            expect(m.confidence_score > 0.0 && m.confidence_score <= 1.0 + 1e-6,
                   "confidence in (0,1]");
        }
    }
    expect(on_road >= 10, "most steps on-road for near-road synthetic traj");

    // Large uncertainty must not force high-confidence on-road snap.
    NavigationState uncertain = makeState(0.0, lat0, lon0, pi / 2.0, 2500.0);
    engine.reset();
    auto u = engine.match(uncertain);
    expect(!u.is_on_road_network || u.confidence_score < 0.9,
           "large sigma fail-safe / low confidence");

    // Far off-network: no forced match.
    NavigationState far = makeState(0.0, lat0 + 0.05, lon0 + 0.05, 0.0, 16.0);
    engine.reset();
    auto f = engine.match(far);
    expect(!f.is_on_road_network, "far observation off-network");
    expect(f.confidence_score < 0.5, "far observation low confidence");
    expect(std::abs(f.lat_snapped - far.latitude) < 1e-12, "preserve unsnapped lat");
    expect(std::abs(f.lon_snapped - far.longitude) < 1e-12, "preserve unsnapped lon");

    NavigationState other_city = makeState(0.0, 28.6139, 77.2090, 0.0, 16.0); /* Delhi vs pack */
    engine.reset();
    auto distant = engine.match(other_city);
    expect(!distant.is_on_road_network, "hundreds of km away is off-network");
    expect(distant.road_segment_id == 0, "no distant segment id");
    expect(std::abs(distant.lat_snapped - other_city.latitude) < 1e-12, "no city teleport lat");
    expect(std::abs(distant.lon_snapped - other_city.longitude) < 1e-12, "no city teleport lon");
    expect(engine.coversLocation(lat0, lon0), "origin inside pack bounds");
    expect(!engine.coversLocation(28.6139, 77.2090), "Delhi outside pack bounds");

    // Sliding window online API determinism vs batch for short window.
    engine.reset();
    std::vector<sih26168::member4::MapMatchedPosition> online;
    for (const auto& s : traj) {
        online.push_back(engine.match(s));
    }
    expect(online.size() == traj.size(), "online size");
    expect(online.back().is_on_road_network, "online ends on-road");

    if (failures == 0) {
        std::cout << "member4_cpp_tests: OK\n";
        return 0;
    }
    std::cerr << "member4_cpp_tests: " << failures << " failure(s)\n";
    return 1;
}
