#include "sih26168/v2x/v2x.hpp"

#include <chrono>
#include <iostream>
#include <vector>

using namespace sih26168::v2x;
using Steady = std::chrono::steady_clock;

int main() {
    V2XConfig cfg{};
    cfg.origin_locked = true;
    V2XCore core(cfg);
    core.lockOrigin(EnuOrigin{12.9716, 77.5946, 920.0, true});

    NormalizedV2XMessage m{};
    m.vehicle_id = "bench";
    m.geo = {12.9717, 77.5946, 920.0};
    m.velocity_enu = {0.0, 15.0, 0.0};
    m.declared_pos_std_m = 3.0;
    m.source = MessageSource::Simulator;
    m.quality = SourceQuality::Medium;

    constexpr int kN = 20000;
    const auto t0 = Steady::now();
    for (int i = 0; i < kN; ++i) {
        m.time.sender_time_s = 0.01 * i;
        m.time.receive_time_s = m.time.sender_time_s + 0.04;
        m.geo.latitude_deg = 12.9716 + 1e-6 * i;
        core.ingest(m);
        LocalNavigationState s{};
        s.valid = true;
        s.timestamp_s = m.time.receive_time_s;
        s.latitude_deg = 12.9716;
        s.longitude_deg = 77.5946;
        s.altitude_m = 920.0;
        s.gnss_available = (i < 100);
        s.v_x = 15.0;
        (void)core.getCooperativeMeasurement(s);
    }
    const auto t1 = Steady::now();
    const double ms =
        std::chrono::duration<double, std::milli>(t1 - t0).count();
    const double avg = ms / kN;
    std::cout << "MODE A host benchmark (NOT Android)\n";
    std::cout << "ingest+measure iterations: " << kN << "\n";
    std::cout << "total_ms: " << ms << "\n";
    std::cout << "avg_ms: " << avg << "\n";
    std::cout << "approx_p95_ms: " << avg * 1.6 << " (host estimate, not measured quantile)\n";
    std::cout << "approx_p99_ms: " << avg * 2.2 << " (host estimate, not measured quantile)\n";
    std::cout << "ANDROID PERFORMANCE: NOT VALIDATED\n";
    return 0;
}
