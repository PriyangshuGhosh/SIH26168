#include "member5/Engine.hpp"

#include <chrono>
#include <cmath>
#include <cstring>
#if defined(IDR_WITH_ONNXRUNTIME)
#include <fstream>
#endif
#include <utility>

namespace sih26168::member5 {
namespace {

constexpr double kRadToDeg = 180.0 / 3.14159265358979323846;

#if defined(IDR_WITH_ONNXRUNTIME)
bool fileExists(const char* path) {
    if (path == nullptr || path[0] == '\0') {
        return false;
    }
    std::ifstream in(path, std::ios::binary);
    return in.good();
}
#endif

double hypotSpeed(double vx, double vy) {
    return std::sqrt(vx * vx + vy * vy);
}

}  // namespace

Engine::Engine() = default;

Engine::~Engine() { stop(); }

bool Engine::start(const char* map_db_path, const char* onnx_model_path) {
    stop();
    aligner_.reset();
    fusion_.reset();
    deficit_.reset();
    imu_q_.clear();
    gnss_q_.clear();
    dropped_imu_.store(0, std::memory_order_relaxed);
    window_.fill(0.0f);
    window_count_ = 0;
    stride_count_ = 0;

    matcher_.loadMap(map_db_path);

    speed_ = std::make_unique<MockSpeedEstimator>();
    backend_name_ = "mock";
#if defined(IDR_WITH_ONNXRUNTIME)
    if (fileExists(onnx_model_path)) {
        auto onnx = std::make_unique<OnnxSpeedEstimator>();
        if (onnx->load(onnx_model_path)) {
            speed_ = std::move(onnx);
            backend_name_ = "onnxruntime";
        }
    }
#endif
    speed_->load(onnx_model_path ? onnx_model_path : "");

    {
        std::lock_guard<std::mutex> lock(state_mu_);
        output_ = IDRNavigationOutput{};
        output_.lat = 12.9716;
        output_.lon = 77.5946;
        output_.is_dead_reckoning = 1;
        output_.confidence = 0.0;
    }

    running_.store(true, std::memory_order_release);
    worker_ = std::thread([this]() { workerLoop(); });
    return true;
}

void Engine::stop() {
    const bool was = running_.exchange(false, std::memory_order_acq_rel);
    if (worker_.joinable()) {
        worker_.join();
    }
    if (was) {
        speed_.reset();
    }
}

bool Engine::feedImu(const ImuSample& s) {
    if (!running_.load(std::memory_order_acquire)) {
        return false;
    }
    if (!imu_q_.push(s)) {
        dropped_imu_.fetch_add(1, std::memory_order_relaxed);
        return false;
    }
    return true;
}

bool Engine::feedGnss(const GnssSample& s) {
    if (!running_.load(std::memory_order_acquire)) {
        return false;
    }
    /* Quality decision is applied immediately so DR mode is visible on the
       C ABI without waiting for the worker thread. */
    const auto mode = deficit_.observe(s.timestamp, s.hdop, s.num_sats);
    {
        std::lock_guard<std::mutex> lock(state_mu_);
        output_.timestamp = s.timestamp;
        output_.is_dead_reckoning =
            (mode == sih26168::member3::NavigationMode::DEAD_RECKONING) ? 1 : 0;
        if (mode == sih26168::member3::NavigationMode::GNSS_AIDED) {
            output_.lat = s.lat;
            output_.lon = s.lon;
            output_.speed_m_s = s.speed;
        }
    }
    return gnss_q_.push(s);
}

IDRNavigationOutput Engine::currentState() const {
    std::lock_guard<std::mutex> lock(state_mu_);
    return output_;
}

void Engine::workerLoop() {
    while (running_.load(std::memory_order_acquire)) {
        bool work = false;
        while (auto g = gnss_q_.pop()) {
            handleGnss(*g);
            work = true;
        }
        while (auto imu = imu_q_.pop()) {
            handleImu(*imu);
            work = true;
        }
        if (!work) {
            std::this_thread::sleep_for(std::chrono::microseconds(500));
        }
    }
}

void Engine::handleGnss(const GnssSample& s) {
    sih26168::member2::OptionalGnssAid aid;
    aid.timestamp = s.timestamp;
    aid.speed_mps = s.speed;
    aid.hdop = s.hdop;
    aid.num_sats = s.num_sats;
    aligner_.feedGnss(aid);

    const auto mode = deficit_.observe(s.timestamp, s.hdop, s.num_sats);
    if (mode == sih26168::member3::NavigationMode::GNSS_AIDED) {
        fusion_.updateGnss(s.timestamp, s.lat, s.lon, s.alt, s.speed);
    }
    publishLocked();
}

void Engine::handleImu(const ImuSample& s) {
    const auto aligned = aligner_.process(s.timestamp, s.ax, s.ay, s.az, s.gx, s.gy, s.gz);
    if (aligned.status == sih26168::member2::CalibrationStatus::INVALID) {
        return;
    }

    const auto mode = deficit_.evaluate(s.timestamp);
    fusion_.predict(aligned, mode);

    const float ch[kChannels] = {
        static_cast<float>(aligned.ax_v), static_cast<float>(aligned.ay_v),
        static_cast<float>(aligned.az_v), static_cast<float>(aligned.gx_v),
        static_cast<float>(aligned.gy_v), static_cast<float>(aligned.gz_v)};

    if (window_count_ < kWindowSamples) {
        for (int c = 0; c < kChannels; ++c) {
            window_[static_cast<std::size_t>(c * kWindowSamples + window_count_)] = ch[c];
        }
        ++window_count_;
    } else {
        for (int c = 0; c < kChannels; ++c) {
            float* row = window_.data() + c * kWindowSamples;
            std::memmove(row, row + 1, static_cast<std::size_t>(kWindowSamples - 1) * sizeof(float));
            row[kWindowSamples - 1] = ch[c];
        }
    }

    ++stride_count_;
    if (window_count_ == kWindowSamples && stride_count_ >= kStride && speed_) {
        stride_count_ = 0;
        const SpeedEstimate est = speed_->predict(window_.data());
        if (est.valid) {
            fusion_.updateAiSpeed(s.timestamp, est.velocity_mps, est.variance_m2s2);
        }
    }

    publishLocked();
}

void Engine::publishLocked() {
    const auto& nav = fusion_.state();
    const auto match = matcher_.match(nav);
    const auto mode = nav.mode;

    IDRNavigationOutput out{};
    out.timestamp = match.timestamp;
    out.lat = match.lat_snapped;
    out.lon = match.lon_snapped;
    out.heading_deg = match.heading_snapped_rad * kRadToDeg;
    out.speed_m_s = hypotSpeed(nav.v_x, nav.v_y);
    out.is_dead_reckoning = (mode == sih26168::member3::NavigationMode::DEAD_RECKONING) ? 1 : 0;
    double conf = match.confidence_score;
    if (out.is_dead_reckoning) {
        conf *= 0.85;
    }
    out.confidence = conf;

    std::lock_guard<std::mutex> lock(state_mu_);
    output_ = out;
}

}  // namespace sih26168::member5
