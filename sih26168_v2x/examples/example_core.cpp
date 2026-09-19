#include "sih26168/v2x/v2x.hpp"

#include <iostream>

int main() {
    using namespace sih26168::v2x;
    V2XConfig cfg{};
    cfg.origin_locked = true;
    V2XCore core(cfg);
    core.lockOrigin(EnuOrigin{12.9716, 77.5946, 920.0, true});

    SimulatedV2XConfig sc{};
    sc.remotes.push_back({"lead", 12.9718, 77.5946, 0.0, 16.0, 0.0, 3.0});
    core.setTransport(makeSimulatedTransport(sc));

    LocalNavigationState local{};
    local.valid = true;
    local.latitude_deg = 12.9716;
    local.longitude_deg = 77.5946;
    local.altitude_m = 920.0;
    local.v_x = 15.0;
    local.yaw_rad = 0.0;

    for (int i = 0; i < 20; ++i) {
        const double t = 0.1 * i;
        local.timestamp_s = t;
        local.gnss_available = t < 1.0;
        core.pollTransport(t);
        const auto r = core.getCooperativeMeasurement(local);
        std::cout << "t=" << t << " decision=" << static_cast<int>(r.decision)
                  << " reason=" << r.reason << " n=" << r.measurement.north_m << "\n";
    }
    std::cout << "status=" << kLibraryStatus << "\n";
    return 0;
}
