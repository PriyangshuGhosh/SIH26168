#pragma once

#include "sih26168/v2x/types.hpp"

#include <memory>
#include <string>
#include <vector>

namespace sih26168::v2x {

// MODE A: simulator, JSONL replay, and in-memory fixtures only.
// This is not a C-V2X/NR-V2X/OBU driver.
class IV2XTransport {
public:
    virtual ~IV2XTransport() = default;
    virtual std::vector<NormalizedV2XMessage> poll(double now_s) = 0;
    virtual std::string name() const = 0;
    virtual bool ok() const { return true; }
};

class InMemoryV2XTransport final : public IV2XTransport {
public:
    void push(NormalizedV2XMessage msg);
    std::vector<NormalizedV2XMessage> poll(double now_s) override;
    std::string name() const override { return "in_memory"; }

private:
    std::vector<NormalizedV2XMessage> queued_;
};

struct SimulatedVehicle {
    std::string id;
    double lat0_deg{0.0};
    double lon0_deg{0.0};
    double heading_rad{0.0};
    double speed_mps{15.0};
    double yaw_rate_rps{0.0};
    double pos_std_m{3.0};
};

struct SimulatedV2XConfig {
    unsigned seed{1};
    double origin_lat_deg{12.9716};
    double origin_lon_deg{77.5946};
    double packet_loss{0.0};
    double latency_s{0.05};
    double jitter_s{0.01};
    double out_of_order_rate{0.0};
    double bad_message_rate{0.0};
    double remote_gps_bias_m{0.0};
    double duplicate_rate{0.0};
    double timestamp_error_s{0.0};
    double velocity_std_mps{0.4};
    double dt_s{0.1};
    std::vector<SimulatedVehicle> remotes;
};

class SimulatedV2XTransport final : public IV2XTransport {
public:
    explicit SimulatedV2XTransport(SimulatedV2XConfig cfg);
    std::vector<NormalizedV2XMessage> poll(double now_s) override;
    std::string name() const override { return "simulated"; }

private:
    SimulatedV2XConfig cfg_{};
    double last_emit_s_{-1.0};
    std::uint64_t rng_{1};
    double nextRand();
};

class ReplayV2XTransport final : public IV2XTransport {
public:
    explicit ReplayV2XTransport(std::string jsonl_path);
    std::vector<NormalizedV2XMessage> poll(double now_s) override;
    std::string name() const override { return "replay"; }
    bool ok() const override { return loaded_; }
    std::size_t size() const { return messages_.size(); }

private:
    std::vector<NormalizedV2XMessage> messages_;
    std::size_t index_{0};
    bool loaded_{false};
};

bool parseNormalizedJson(std::string_view json, NormalizedV2XMessage& out, std::string& error);
std::string serializeNormalizedJson(const NormalizedV2XMessage& msg);

std::unique_ptr<IV2XTransport> makeSimulatedTransport(const SimulatedV2XConfig& cfg);
std::unique_ptr<IV2XTransport> makeReplayTransport(const std::string& path);

}  // namespace sih26168::v2x
