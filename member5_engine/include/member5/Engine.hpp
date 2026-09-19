#pragma once

#include "idr_engine_api.h"
#include "member2/FrameAligner.hpp"
#include "member3/EKFFusionEngine.hpp"
#include "member4/MapMatchingEngine.hpp"
#include "member5/GnssDeficitMachine.hpp"
#include "member5/MapCatalog.hpp"
#include "member5/SpeedEstimator.hpp"
#include "member5/SpeedValidity.hpp"
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

/* Maps a GNSS sample to the Member 3 measurement. Missing/invalid speed (NaN, negative or inf;
   e.g. Android Location.hasSpeed() == false) becomes speed_valid = false so the EKF applies the
   position only. A real 0.0 m/s (stationary) stays a valid speed measurement. */
sih26168::member3::GnssMeasurement toGnssMeasurement(const GnssSample& s);

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

    int selectMapForLocation(double lat, double lon);
    int mapCoversLocation(double lat, double lon) const;
    const char* activeMapRegionId() const;
    const char* mapStatusMessage() const;
    const char* speedRejectReason() const;
    IDRDiagnostics diagnostics() const;
    int speedIsValid() const;

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
    bool applyRoadpack(const std::string& path);
    void noteImuRate(double timestamp);

    SpscRing<ImuSample, 2048> imu_q_;
    SpscRing<GnssSample, 128> gnss_q_;
    std::atomic<std::uint64_t> dropped_imu_{0};

    sih26168::member2::FrameAligner aligner_;
    std::unique_ptr<ISpeedEstimator> speed_;
    sih26168::member3::EKFFusionEngine fusion_;
    sih26168::member4::MapMatchingEngine matcher_;
    GnssDeficitMachine deficit_;
    MapCatalog catalog_;
    SpeedValidityFilter speed_guard_;
    SpeedValidityFilter ai_guard_;
    SpeedValidityConfig speed_cfg_{};

    std::array<float, kMaxT * kChannels> window_{};
    int window_count_{0};
    int stride_count_{0};
    int model_T_{200};

    mutable std::mutex state_mu_;
    IDRNavigationOutput output_{};
    IDRDiagnostics diagnostics_{};
    std::int64_t road_segment_id_{0};
    int is_on_road_{0};
    int speed_valid_{0};
    std::string speed_reject_;
    std::string active_region_id_;
    std::string map_status_;
    MapCoverage map_coverage_{MapCoverage::Unknown};
    double last_ai_speed_{0.0};
    double last_gnss_speed_{0.0};
    double last_ekf_speed_{0.0};
    double last_imu_t_{0.0};
    double last_gnss_t_{0.0};
    double imu_hz_{0.0};
    double imu_rate_t_{0.0};
    int imu_rate_n_{0};
    int last_ai_accepted_{0};
    int last_cal_status_{0};

    std::atomic<bool> running_{false};
    std::thread worker_;
    std::string backend_name_;
    std::string last_error_;
    bool using_mock_speed_{false};
    bool catalog_mode_{false};
};

}  // namespace sih26168::member5
