#pragma once

#include "idr_engine_api.h"
#include "member2/FrameAligner.hpp"
#include "member3/EKFFusionEngine.hpp"
#include "member4/MapMatchingEngine.hpp"
#include "member5/GnssDeficitMachine.hpp"
#include "member5/SpeedEstimator.hpp"
#include "member5/SpscRing.hpp"

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
    std::int64_t roadSegmentId() const;
    int isOnRoadNetwork() const;
    const char* lastError() const { return last_error_.c_str(); }
    const char* speedBackend() const { return backend_name_.c_str(); }
    std::uint64_t droppedImu() const { return dropped_imu_.load(std::memory_order_relaxed); }

    static bool mockSpeedRequested(const char* onnx_model_path);

private:
    static constexpr int kChannels = 6;
    static constexpr int kImuHz = 100;
    static constexpr int kStride = 10; /* handbook: 10 samples at 100 Hz */
    static constexpr int kMaxT = 400;  /* 4 s at 100 Hz */
    static_assert(kImuHz == 100, "Member 1 live IMU rate is 100 Hz");

    void workerLoop();
    void handleGnss(const GnssSample& s);
    void handleImu(const ImuSample& s);
    void pushAlignedSample(const float* ch6);
    void publishLocked();
    bool loadMap(const char* map_db_path);
    bool loadSpeed(const char* onnx_model_path);

    SpscRing<ImuSample, 2048> imu_q_;
    SpscRing<GnssSample, 128> gnss_q_;
    std::atomic<std::uint64_t> dropped_imu_{0};

    sih26168::member2::FrameAligner aligner_;
    std::unique_ptr<ISpeedEstimator> speed_;
    sih26168::member3::EKFFusionEngine fusion_;
    sih26168::member4::MapMatchingEngine matcher_;
    GnssDeficitMachine deficit_;

    std::array<float, kMaxT * kChannels> window_{};
    int window_count_{0};
    int stride_count_{0};
    int model_T_{200};

    mutable std::mutex state_mu_;
    IDRNavigationOutput output_{};
    std::int64_t road_segment_id_{0};
    int is_on_road_{0};

    std::atomic<bool> running_{false};
    std::thread worker_;
    std::string backend_name_;
    std::string last_error_;
    bool using_mock_speed_{false};
};

}  // namespace sih26168::member5
