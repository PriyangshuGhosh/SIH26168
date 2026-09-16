#pragma once

#include "idr_engine_api.h"
#include "member2/FrameAligner.hpp"
#include "member5/GnssDeficitMachine.hpp"
#include "member5/SpeedEstimator.hpp"
#include "member5/SpscRing.hpp"
#include "member5/StubFusionEngine.hpp"
#include "member5/StubMapMatcher.hpp"

#include <array>
#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

namespace sih26168::member5 {

struct ImuSample {
    double timestamp;
    double ax, ay, az;
    double gx, gy, gz;
};

struct GnssSample {
    double timestamp;
    double lat, lon, alt;
    double speed;
    double hdop;
    int num_sats;
};

class Engine {
public:
    Engine();
    ~Engine();

    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;

    bool start(const char* map_db_path, const char* onnx_model_path);
    void stop();

    bool feedImu(const ImuSample& s);
    bool feedGnss(const GnssSample& s);
    IDRNavigationOutput currentState() const;
    std::uint64_t droppedImu() const { return dropped_imu_.load(std::memory_order_relaxed); }

private:
    static constexpr int kWindowSamples = 200;
    static constexpr int kChannels = 6;
    static constexpr int kStride = 10;

    void workerLoop();
    void handleGnss(const GnssSample& s);
    void handleImu(const ImuSample& s);
    void publishLocked();

    SpscRing<ImuSample, 2048> imu_q_;
    SpscRing<GnssSample, 128> gnss_q_;
    std::atomic<std::uint64_t> dropped_imu_{0};

    sih26168::member2::FrameAligner aligner_;
    std::unique_ptr<ISpeedEstimator> speed_;
    StubFusionEngine fusion_;
    StubMapMatcher matcher_;
    GnssDeficitMachine deficit_;

    std::array<float, kChannels * kWindowSamples> window_{};
    int window_count_{0};
    int stride_count_{0};

    mutable std::mutex state_mu_;
    IDRNavigationOutput output_{};

    std::atomic<bool> running_{false};
    std::thread worker_;
    std::string backend_name_;
};

}  // namespace sih26168::member5
