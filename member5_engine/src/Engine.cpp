#include "member5/Engine.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <string>

namespace sih26168::member5 {
namespace {

constexpr double kRadToDeg = 180.0 / 3.14159265358979323846;

bool fileExists(const char* path) {
    if (path == nullptr || path[0] == '\0') {
        return false;
    }
    std::ifstream in(path, std::ios::binary);
    return in.good();
}

bool envTruthy(const char* name) {
    const char* v = std::getenv(name);
    if (v == nullptr || v[0] == '\0') {
        return false;
    }
    return v[0] == '1' || v[0] == 't' || v[0] == 'T' || v[0] == 'y' || v[0] == 'Y';
}

bool startsWith(const char* s, const char* pfx) {
    if (s == nullptr || pfx == nullptr) {
        return false;
    }
    const std::size_t n = std::strlen(pfx);
    return std::strncmp(s, pfx, n) == 0;
}

bool endsWith(const std::string& s, const char* suf) {
    const std::size_t n = std::strlen(suf);
    return s.size() >= n && s.compare(s.size() - n, n, suf) == 0;
}

double hypotSpeed(double vx, double vy) {
    return std::sqrt(vx * vx + vy * vy);
}

std::string extLower(const std::string& path) {
    const auto dot = path.find_last_of('.');
    if (dot == std::string::npos) {
        return {};
    }
    std::string e = path.substr(dot);
    for (char& c : e) {
        if (c >= 'A' && c <= 'Z') {
            c = static_cast<char>(c - 'A' + 'a');
        }
    }
    return e;
}

}  // namespace

Engine::Engine() = default;

Engine::~Engine() { stop(); }

bool Engine::mockSpeedRequested(const char* onnx_model_path) {
    if (onnx_model_path != nullptr) {
        if (std::strcmp(onnx_model_path, "mock") == 0 || startsWith(onnx_model_path, "mock:")) {
            return true;
        }
    }
    return envTruthy("SIH26168_ALLOW_MOCK_SPEED");
}

bool Engine::start(const char* map_db_path, const char* onnx_model_path) {
    stop();
    last_error_.clear();
    aligner_.reset();
    fusion_.reset();
    matcher_.reset();
    deficit_.reset();
    imu_q_.clear();
    gnss_q_.clear();
    dropped_imu_.store(0, std::memory_order_relaxed);
    window_.fill(0.0f);
    window_count_ = 0;
    stride_count_ = 0;
    model_T_ = 200;
    using_mock_speed_ = false;
    backend_name_ = "none";
    catalog_mode_ = false;
    speed_guard_ = SpeedValidityFilter(speed_cfg_);
    ai_guard_ = SpeedValidityFilter(speed_cfg_);
    active_region_id_.clear();
    map_status_ = "unknown";
    map_coverage_ = MapCoverage::Unknown;
    speed_reject_.clear();
    speed_valid_ = 0;
    last_ai_speed_ = 0.0;
    last_gnss_speed_ = 0.0;
    last_ekf_speed_ = 0.0;

    if (!loadMap(map_db_path)) {
        return false;
    }
    if (!loadSpeed(onnx_model_path)) {
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(state_mu_);
        output_ = IDRNavigationOutput{};
        output_.is_dead_reckoning = 1;
        output_.confidence = 0.0;
        road_segment_id_ = 0;
        is_on_road_ = 0;
        speed_valid_ = 0;
        diagnostics_ = IDRDiagnostics{};
    }

    running_.store(true, std::memory_order_release);
    worker_ = std::thread([this]() { workerLoop(); });
    return true;
}

bool Engine::applyRoadpack(const std::string& path) {
    if (!matcher_.loadRoadpack(path)) {
        last_error_ = matcher_.lastError().empty() ? ("invalid roadpack: " + path) : matcher_.lastError();
        return false;
    }
    if (!matcher_.hasMap()) {
        last_error_ = "roadpack contained no segments: " + path;
        return false;
    }
    double min_lat = 0, max_lat = 0, min_lon = 0, max_lon = 0;
    if (!catalog_mode_ && matcher_.geographicBounds(min_lat, max_lat, min_lon, max_lon)) {
        catalog_.setBoundsFromGeometry(min_lat, max_lat, min_lon, max_lon);
    }
    return true;
}

bool Engine::loadMap(const char* map_db_path) {
    const std::string path = (map_db_path != nullptr) ? map_db_path : "";
    catalog_mode_ = false;
    if (path.empty()) {
        last_error_ = "map_db_path is required (offline .roadpack or maps/manifest.json)";
        return false;
    }
    if (path == "mock" || startsWith(path.c_str(), "mock:")) {
        last_error_ = "production requires a real .roadpack; mock maps are not supported";
        return false;
    }
    const std::string ext = extLower(path);
    if (ext == ".graphml" || ext == ".geojson" || ext == ".xml") {
        last_error_ =
            "C++ MapMatchingEngine loads .roadpack only (convert GraphML/GeoJSON with "
            "member4_map_matching/python/tools/build_road_database.py)";
        return false;
    }
    if (endsWith(path, "manifest.json") || endsWith(path, "/maps") || endsWith(path, "\\maps")) {
        std::string manifest = path;
        if (!endsWith(path, "manifest.json")) {
            manifest = path + "/manifest.json";
        }
        if (!catalog_.loadManifestFile(manifest)) {
            last_error_ = catalog_.lastError();
            return false;
        }
        catalog_mode_ = true;
        map_status_ = "catalog_loaded_awaiting_location";
        map_coverage_ = MapCoverage::Unknown;
        active_region_id_.clear();
        return true;
    }
    if (!fileExists(path.c_str())) {
        last_error_ = "map file not found: " + path;
        return false;
    }
    if (!catalog_.loadSingleRoadpack(path, "provisioned")) {
        last_error_ = catalog_.lastError();
        return false;
    }
    if (!applyRoadpack(path)) {
        return false;
    }
    active_region_id_ = "provisioned";
    map_status_ = "single_roadpack_loaded";
    map_coverage_ = MapCoverage::Unknown;
    return true;
}

bool Engine::loadSpeed(const char* onnx_model_path) {
    const bool mock = mockSpeedRequested(onnx_model_path);
    using_mock_speed_ = mock;
    if (mock) {
        speed_ = std::make_unique<MockSpeedEstimator>();
        speed_->load(onnx_model_path ? onnx_model_path : "");
        backend_name_ = speed_->backendName();
        model_T_ = speed_->requiredWindowSamples();
        return true;
    }

#if defined(IDR_WITH_ONNXRUNTIME)
    if (onnx_model_path == nullptr || onnx_model_path[0] == '\0') {
        last_error_ = "onnx_model_path is required in production (pass \"mock\" only for tests)";
        return false;
    }
    /* Opt-in stateful streaming candidate (member1-ml/docs/gru_velocity.md), same "explicit prefix
       marker" convention as "mock:" above. Unmarked paths keep using the existing stateless
       OnnxSpeedEstimator unchanged -- this branch does not alter default behaviour at all. */
    if (startsWith(onnx_model_path, "gru:")) {
        const std::string path = onnx_model_path + 4;
        if (!fileExists(path.c_str())) {
            last_error_ = std::string("GRU streaming ONNX model not found: ") + path;
            return false;
        }
        auto gru = std::make_unique<GruStreamingSpeedEstimator>();
        if (!gru->load(path)) {
            last_error_ = gru->lastError()[0] != '\0'
                              ? std::string(gru->lastError())
                              : (std::string("failed to load GRU streaming ONNX model: ") + path);
            return false;
        }
        speed_ = std::move(gru);
        speed_->reset(); /* explicit startup reset; also true by construction (see class docstring) */
        backend_name_ = speed_->backendName();
        model_T_ = std::clamp(speed_->requiredWindowSamples(), 8, kMaxT);
        return true;
    }
    if (!fileExists(onnx_model_path)) {
        last_error_ = std::string("ONNX model not found: ") + onnx_model_path;
        return false;
    }
    auto onnx = std::make_unique<OnnxSpeedEstimator>();
    if (!onnx->load(onnx_model_path)) {
        last_error_ = onnx->lastError()[0] != '\0'
                          ? std::string(onnx->lastError())
                          : (std::string("failed to load ONNX model: ") + onnx_model_path);
        return false;
    }
    speed_ = std::move(onnx);
    backend_name_ = speed_->backendName();
    model_T_ = std::clamp(speed_->requiredWindowSamples(), 8, kMaxT);
    return true;
#else
    last_error_ =
        "production build has no ONNX Runtime; rebuild with -DIDR_WITH_ONNXRUNTIME=ON or pass "
        "onnx_model_path=\"mock\" for explicit test/dev mock";
    return false;
#endif
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
    const auto mode = deficit_.observe(s.timestamp, s.hdop, s.num_sats);
    last_gnss_speed_ = s.speed;
    last_gnss_t_ = s.timestamp;
    {
        std::lock_guard<std::mutex> lock(state_mu_);
        output_.timestamp = s.timestamp;
        output_.is_dead_reckoning =
            (mode == sih26168::member3::NavigationMode::DEAD_RECKONING) ? 1 : 0;
        if (mode == sih26168::member3::NavigationMode::GNSS_AIDED) {
            output_.lat = s.lat;
            output_.lon = s.lon;
            if (SpeedValidityFilter::finiteNonNegative(s.speed) &&
                s.speed <= speed_cfg_.max_vehicle_speed_mps) {
                output_.speed_m_s = s.speed;
                speed_valid_ = 1;
                speed_reject_.clear();
            } else {
                speed_valid_ = 0;
                speed_reject_ = std::isfinite(s.speed) ? "gnss_speed_rejected" : "gnss_speed_unavailable";
            }
        }
    }
    return gnss_q_.push(s);
}

IDRNavigationOutput Engine::currentState() const {
    std::lock_guard<std::mutex> lock(state_mu_);
    return output_;
}

std::int64_t Engine::roadSegmentId() const {
    std::lock_guard<std::mutex> lock(state_mu_);
    return road_segment_id_;
}

int Engine::isOnRoadNetwork() const {
    std::lock_guard<std::mutex> lock(state_mu_);
    return is_on_road_;
}

int Engine::speedIsValid() const {
    std::lock_guard<std::mutex> lock(state_mu_);
    return speed_valid_;
}

const char* Engine::speedRejectReason() const { return speed_reject_.c_str(); }
const char* Engine::activeMapRegionId() const { return active_region_id_.c_str(); }
const char* Engine::mapStatusMessage() const { return map_status_.c_str(); }

int Engine::mapCoversLocation(double lat, double lon) const {
    std::lock_guard<std::mutex> lock(state_mu_);
    if (matcher_.hasMap() && matcher_.coversLocation(lat, lon)) {
        return 1;
    }
    return catalog_.covers(lat, lon) ? 1 : 0;
}

int Engine::selectMapForLocation(double lat, double lon) {
    /* Not on the 100 Hz IMU callback. GNSS/UI thread only. */
    std::lock_guard<std::mutex> lock(state_mu_);
    if (!std::isfinite(lat) || !std::isfinite(lon)) {
        map_coverage_ = MapCoverage::Unknown;
        map_status_ = "MAP DATA NOT AVAILABLE";
        return 0;
    }
    if (matcher_.hasMap() && matcher_.coversLocation(lat, lon)) {
        map_coverage_ = MapCoverage::InRegion;
        map_status_ = "in_region";
        if (active_region_id_.empty()) {
            active_region_id_ = "provisioned";
        }
        return 1;
    }
    const MapRegion* r = catalog_.findCovering(lat, lon);
    if (r == nullptr) {
        map_coverage_ =
            catalog_.regions().empty() ? MapCoverage::NoPackage : MapCoverage::OutOfRegion;
        map_status_ = "MAP DATA NOT AVAILABLE";
        return 0;
    }
    if (!(active_region_id_ == r->id && matcher_.hasMap())) {
        if (!applyRoadpack(r->roadpack_path)) {
            map_coverage_ = MapCoverage::NoPackage;
            map_status_ = "MAP DATA NOT AVAILABLE";
            return 0;
        }
        active_region_id_ = r->id;
    }
    if (!matcher_.coversLocation(lat, lon)) {
        map_coverage_ = MapCoverage::OutOfRegion;
        map_status_ = "MAP DATA NOT AVAILABLE";
        return 0;
    }
    map_coverage_ = MapCoverage::InRegion;
    map_status_ = "in_region";
    return 1;
}

IDRDiagnostics Engine::diagnostics() const {
    std::lock_guard<std::mutex> lock(state_mu_);
    return diagnostics_;
}

void Engine::noteImuRate(double timestamp) {
    if (!std::isfinite(timestamp)) {
        return;
    }
    if (imu_rate_n_ == 0) {
        imu_rate_t_ = timestamp;
        imu_rate_n_ = 1;
        return;
    }
    ++imu_rate_n_;
    const double dt = timestamp - imu_rate_t_;
    if (dt >= 0.5) {
        imu_hz_ = static_cast<double>(imu_rate_n_ - 1) / dt;
        imu_rate_t_ = timestamp;
        imu_rate_n_ = 1;
    }
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

sih26168::member3::GnssMeasurement toGnssMeasurement(const GnssSample& s) {
    sih26168::member3::GnssMeasurement g;
    g.timestamp = s.timestamp;
    g.latitude = s.lat;
    g.longitude = s.lon;
    g.altitude = s.alt;
    g.speed_mps = s.speed;
    g.speed_valid = SpeedValidityFilter::finiteNonNegative(s.speed);
    g.hdop = s.hdop;
    g.num_sats = s.num_sats;
    return g;
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
        fusion_.updateGnss(toGnssMeasurement(s));
    }
    publishLocked();
}

void Engine::handleImu(const ImuSample& s) {
    const auto aligned = aligner_.process(s.timestamp, s.ax, s.ay, s.az, s.gx, s.gy, s.gz);
    if (aligned.status == sih26168::member2::CalibrationStatus::INVALID) {
        /* The one discontinuity condition Engine already special-cases: this raw sample is
           discarded entirely (no predict()/EKF update below), so a stateful speed estimator's
           hidden state is cleared here too rather than carried across the gap -- a no-op for the
           stateless MockSpeedEstimator/OnnxSpeedEstimator (default reset()). */
        if (speed_) {
            speed_->reset();
        }
        return;
    }

    const auto mode = deficit_.evaluate(s.timestamp);
    fusion_.predict(aligned, mode);
    last_cal_status_ = static_cast<int>(aligned.status);
    last_imu_t_ = s.timestamp;
    noteImuRate(s.timestamp);

    const float ch[kChannels] = {
        static_cast<float>(aligned.ax_v / 9.80665f), static_cast<float>(aligned.ay_v / 9.80665f),
        static_cast<float>(aligned.az_v / 9.80665f), static_cast<float>(aligned.gx_v),
        static_cast<float>(aligned.gy_v), static_cast<float>(aligned.gz_v)};

    ++stride_count_;
    pushAlignedSample(ch);
    if (speed_ && window_count_ >= model_T_ && stride_count_ >= kStride) {
        stride_count_ = 0;
        const int src0 = window_count_ - model_T_;
        SpeedEstimate est =
            speed_->predict(window_.data() + src0 * kChannels, model_T_);
        
        if (aligned.status == sih26168::member2::CalibrationStatus::STATIC_DETECTED) {
            est.velocity_mps = 0.0f;
            est.valid = true;
        }

        if (est.valid) {
            last_ai_speed_ = static_cast<double>(est.velocity_mps);
            SpeedRejectReason why = SpeedRejectReason::None;
            const double var = std::max(static_cast<double>(est.variance_m2s2),
                                        speed_cfg_.min_speed_variance_m2s2);
            if (ai_guard_.acceptAiMeasurement(s.timestamp, last_ai_speed_, var, &why)) {
                sih26168::member3::AiSpeedMeasurement meas;
                meas.timestamp = s.timestamp;
                meas.velocity_mps = last_ai_speed_;
                meas.variance_m2s2 = var;
                meas.valid = true;
                fusion_.updateAiSpeed(meas);
                last_ai_accepted_ = fusion_.state().last_ai_speed_accepted ? 1 : 0;
                if (!fusion_.state().last_ai_speed_accepted) {
                    speed_reject_ = "ekf_innovation_rejected";
                }
            } else {
                last_ai_accepted_ = 0;
                speed_reject_ = speedRejectReasonCString(why);
            }
        }
    }

    publishLocked();
}

void Engine::pushAlignedSample(const float* ch6) {
    if (window_count_ < kMaxT) {
        std::memcpy(window_.data() + window_count_ * kChannels, ch6, kChannels * sizeof(float));
        ++window_count_;
        return;
    }
    std::memmove(window_.data(), window_.data() + kChannels,
                 static_cast<std::size_t>(kMaxT - 1) * kChannels * sizeof(float));
    std::memcpy(window_.data() + (kMaxT - 1) * kChannels, ch6, kChannels * sizeof(float));
}

void Engine::publishLocked() {
    const auto& nav = fusion_.state();
    const auto match = matcher_.match(nav);
    const auto mode = nav.mode;
    const double ekf_speed = hypotSpeed(nav.v_x, nav.v_y);
    last_ekf_speed_ = ekf_speed;

    SpeedRejectReason why = SpeedRejectReason::None;
    double publish_speed = ekf_speed;
    int valid = 0;
    if (nav.last_velocity_recovered) {
        why = SpeedRejectReason::RecoveredDivergence;
        if (speed_guard_.haveTrusted()) {
            publish_speed = speed_guard_.lastTrustedMps();
        } else {
            publish_speed = 0.0;
        }
        speed_reject_ = speedRejectReasonCString(why);
    } else if (speed_guard_.accept(nav.timestamp, ekf_speed, &why)) {
        publish_speed = ekf_speed;
        valid = 1;
        speed_reject_.clear();
    } else {
        if (speed_guard_.haveTrusted()) {
            publish_speed = speed_guard_.lastTrustedMps();
        } else {
            publish_speed = 0.0;
        }
        speed_reject_ = speedRejectReasonCString(why);
    }

    IDRNavigationOutput out{};
    out.timestamp = match.timestamp != 0.0 ? match.timestamp : nav.timestamp;
    out.lat = match.lat_snapped;
    out.lon = match.lon_snapped;
    out.heading_deg = match.heading_snapped_rad * kRadToDeg;
    out.speed_m_s = publish_speed;
    out.is_dead_reckoning = (mode == sih26168::member3::NavigationMode::DEAD_RECKONING) ? 1 : 0;
    double conf = match.confidence_score;
    if (out.is_dead_reckoning) {
        conf *= 0.85;
    }
    if (!valid) {
        conf *= 0.4;
    }
    out.confidence = conf;

    IDRDiagnostics d{};
    d.raw_gnss_speed_mps = last_gnss_speed_;
    d.ai_speed_mps = last_ai_speed_;
    d.ekf_speed_mps = ekf_speed;
    d.displayed_speed_mps = publish_speed;
    d.speed_valid = valid;
    d.map_status = static_cast<int>(map_coverage_);
    d.calibration_status = last_cal_status_;
    d.last_ai_speed_accepted = last_ai_accepted_;
    d.imu_hz = imu_hz_;
    d.last_imu_timestamp = last_imu_t_;
    d.last_gnss_timestamp = last_gnss_t_;

    std::lock_guard<std::mutex> lock(state_mu_);
    output_ = out;
    diagnostics_ = d;
    road_segment_id_ = match.road_segment_id;
    is_on_road_ = match.is_on_road_network ? 1 : 0;
    speed_valid_ = valid;
}

}  // namespace sih26168::member5
