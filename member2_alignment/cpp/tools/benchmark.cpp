#include "member2/FrameAligner.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <vector>

int main() {
    using clock = std::chrono::steady_clock;
    using sih26168::member2::FrameAligner;

    FrameAligner aligner;
    constexpr int kWarmup = 2000;
    constexpr int kSamples = 100000;
    const double dt = 0.01;
    double t = 0.0;

    for (int i = 0; i < kWarmup; ++i) {
        const double ax = 0.0;
        const double ay = 0.0;
        const double az = 9.80665;
        aligner.process(t, ax, ay, az, 0.0, 0.0, 0.0);
        t += dt;
    }

    std::vector<double> ns;
    ns.reserve(static_cast<std::size_t>(kSamples));
    double dummy = 0.0;
    for (int i = 0; i < kSamples; ++i) {
        const double ax = 0.2 * std::sin(0.01 * i);
        const double ay = 0.05 * std::cos(0.02 * i);
        const double az = 9.80665 + 0.03 * std::sin(0.03 * i);
        const double gx = 0.001 * std::sin(0.04 * i);
        const double gy = 0.002 * std::cos(0.05 * i);
        const double gz = 0.01 * std::sin(0.01 * i);
        const auto t0 = clock::now();
        const auto out = aligner.process(t, ax, ay, az, gx, gy, gz);
        const auto t1 = clock::now();
        dummy += out.ax_v + out.q_pv[0];
        ns.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count());
        t += dt;
    }

    std::vector<double> sorted = ns;
    std::sort(sorted.begin(), sorted.end());
    auto pct = [&](double p) {
        const std::size_t idx = static_cast<std::size_t>(p * (sorted.size() - 1));
        return sorted[idx];
    };
    double sum = 0.0;
    for (double v : ns) {
        sum += v;
    }
    const double avg = sum / static_cast<double>(ns.size());
    std::cout << std::fixed << std::setprecision(3);
    std::cout << "member2_benchmark\n";
    std::cout << "samples " << kSamples << "\n";
    std::cout << "avg_ns " << avg << "\n";
    std::cout << "p50_ns " << pct(0.50) << "\n";
    std::cout << "p95_ns " << pct(0.95) << "\n";
    std::cout << "p99_ns " << pct(0.99) << "\n";
    std::cout << "max_ns " << sorted.back() << "\n";
    std::cout << "budget_100hz_ns " << 1.0e7 << "\n";
    const double throughput_hz = 1.0e9 / avg;
    std::cout << "throughput_hz " << throughput_hz << "\n";
    std::cout << "sustains_100hz " << (avg < 1.0e7 ? 1 : 0) << "\n";
    std::cout << "sink " << dummy << "\n";
    return (avg < 1.0e7 && std::isfinite(avg)) ? 0 : 1;
}
