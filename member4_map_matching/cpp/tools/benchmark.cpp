#include "member4/MapMatchingEngine.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

static std::string findRoadpack() {
    const char* env = std::getenv("MEMBER4_ROADPACK");
    if (env && fs::exists(env)) {
        return env;
    }
    if (fs::exists("member4_map_matching/data/synthetic_grid.roadpack")) {
        return "member4_map_matching/data/synthetic_grid.roadpack";
    }
    return {};
}

int main() {
    const std::string pack = findRoadpack();
    if (pack.empty()) {
        std::cerr << "missing synthetic_grid.roadpack\n";
        return 1;
    }

    sih26168::member4::MapMatchingEngine engine;
    if (!engine.loadRoadpack(pack)) {
        std::cerr << engine.lastError() << "\n";
        return 1;
    }

    constexpr double lat0 = 12.9716;
    constexpr double lon0 = 77.5946;
    constexpr double pi = 3.14159265358979323846;
    const double dlat = 4.0 / 111320.0;

    std::vector<sih26168::member3::NavigationState> states;
    for (int i = 0; i < 300; ++i) {
        sih26168::member3::NavigationState s;
        s.timestamp = static_cast<double>(i);
        s.latitude = lat0 + i * dlat;
        s.longitude = lon0;
        s.yaw_rad = 0.0;
        s.position_cov_m2[0][0] = 25.0;
        s.position_cov_m2[1][1] = 25.0;
        states.push_back(s);
    }

    // warmup
    for (int i = 0; i < 10; ++i) {
        engine.match(states[i]);
    }
    engine.reset();

    std::vector<double> samples_ms;
    samples_ms.reserve(states.size());
    for (const auto& s : states) {
        const auto t0 = std::chrono::steady_clock::now();
        engine.match(s);
        const auto t1 = std::chrono::steady_clock::now();
        samples_ms.push_back(
            std::chrono::duration<double, std::milli>(t1 - t0).count());
    }
    std::sort(samples_ms.begin(), samples_ms.end());
    auto pct = [&](double p) {
        const double k = (samples_ms.size() - 1) * (p / 100.0);
        const std::size_t f = static_cast<std::size_t>(k);
        const std::size_t c = std::min(f + 1, samples_ms.size() - 1);
        if (f == c) {
            return samples_ms[f];
        }
        return samples_ms[f] + (samples_ms[c] - samples_ms[f]) * (k - f);
    };

    double mean = 0.0;
    for (double v : samples_ms) {
        mean += v;
    }
    mean /= static_cast<double>(samples_ms.size());

    std::cout << "platform=desktop_cpp\n";
    std::cout << "android_performance=NOT_VALIDATED\n";
    std::cout << "n=" << samples_ms.size() << "\n";
    std::cout << "mean_ms=" << mean << "\n";
    std::cout << "p50_ms=" << pct(50) << "\n";
    std::cout << "p95_ms=" << pct(95) << "\n";
    std::cout << "p99_ms=" << pct(99) << "\n";

    fs::create_directories("member4_map_matching/results");
    std::ofstream out("member4_map_matching/results/runtime_cpp.json");
    out << "{\n"
        << "  \"platform\": \"desktop_cpp\",\n"
        << "  \"android_performance\": \"NOT_VALIDATED\",\n"
        << "  \"n\": " << samples_ms.size() << ",\n"
        << "  \"mean_ms\": " << mean << ",\n"
        << "  \"p50_ms\": " << pct(50) << ",\n"
        << "  \"p95_ms\": " << pct(95) << ",\n"
        << "  \"p99_ms\": " << pct(99) << "\n"
        << "}\n";
    return 0;
}
