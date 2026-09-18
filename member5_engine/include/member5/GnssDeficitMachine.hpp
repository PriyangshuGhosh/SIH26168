#pragma once

#include "member3/EKFFusionEngine.hpp"

#include <atomic>
#include <cmath>

namespace sih26168::member5 {

struct GnssDeficitConfig {
    double max_hdop{4.0};
    int min_sats{4};
    double max_age_s{1.2};
};

class GnssDeficitMachine {
public:
    explicit GnssDeficitMachine(const GnssDeficitConfig& cfg = GnssDeficitConfig{}) : cfg_(cfg) {}

    void reset() {
        have_fix_.store(0, std::memory_order_relaxed);
        last_t_.store(0.0, std::memory_order_relaxed);
        last_quality_ok_.store(0, std::memory_order_relaxed);
        mode_.store(static_cast<int>(sih26168::member3::NavigationMode::DEAD_RECKONING),
                    std::memory_order_relaxed);
    }

    sih26168::member3::NavigationMode observe(double timestamp, double hdop, int num_sats) {
        have_fix_.store(1, std::memory_order_release);
        last_t_.store(timestamp, std::memory_order_release);
        const int ok = qualityOk(hdop, num_sats, cfg_) ? 1 : 0;
        last_quality_ok_.store(ok, std::memory_order_release);
        const auto m = ok ? sih26168::member3::NavigationMode::GNSS_AIDED
                          : sih26168::member3::NavigationMode::DEAD_RECKONING;
        mode_.store(static_cast<int>(m), std::memory_order_release);
        return m;
    }

    sih26168::member3::NavigationMode evaluate(double now) {
        if (have_fix_.load(std::memory_order_acquire) == 0 || !std::isfinite(now)) {
            return store(sih26168::member3::NavigationMode::DEAD_RECKONING);
        }
        const double last = last_t_.load(std::memory_order_acquire);
        if (!std::isfinite(last)) {
            return store(sih26168::member3::NavigationMode::DEAD_RECKONING);
        }
        const double age = now - last;
        const bool ok = last_quality_ok_.load(std::memory_order_acquire) != 0;
        if (age > cfg_.max_age_s || !ok) {
            return store(sih26168::member3::NavigationMode::DEAD_RECKONING);
        }
        return store(sih26168::member3::NavigationMode::GNSS_AIDED);
    }

    sih26168::member3::NavigationMode mode() const {
        return static_cast<sih26168::member3::NavigationMode>(mode_.load(std::memory_order_acquire));
    }
    bool haveFix() const { return have_fix_.load(std::memory_order_acquire) != 0; }
    double lastTimestamp() const { return last_t_.load(std::memory_order_acquire); }
    const GnssDeficitConfig& config() const { return cfg_; }

    static bool qualityOk(double hdop, int num_sats, const GnssDeficitConfig& cfg = GnssDeficitConfig{}) {
        return std::isfinite(hdop) && hdop <= cfg.max_hdop && num_sats >= cfg.min_sats;
    }

private:
    sih26168::member3::NavigationMode store(sih26168::member3::NavigationMode m) {
        mode_.store(static_cast<int>(m), std::memory_order_release);
        return m;
    }

    GnssDeficitConfig cfg_{};
    std::atomic<int> have_fix_{0};
    std::atomic<double> last_t_{0.0};
    std::atomic<int> last_quality_ok_{0};
    std::atomic<int> mode_{static_cast<int>(sih26168::member3::NavigationMode::DEAD_RECKONING)};
};

}  // namespace sih26168::member5
