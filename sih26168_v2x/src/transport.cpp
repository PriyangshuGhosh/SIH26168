#include "sih26168/v2x/transport.hpp"

#include "sih26168/v2x/frames.hpp"

#include <cctype>
#include <cmath>
#include <fstream>
#include <sstream>
#include <utility>

namespace sih26168::v2x {
namespace {

void skipWs(std::string_view s, std::size_t& i) {
    while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i]))) {
        ++i;
    }
}

bool parseString(std::string_view s, std::size_t& i, std::string& out) {
    skipWs(s, i);
    if (i >= s.size() || s[i] != '"') {
        return false;
    }
    ++i;
    out.clear();
    while (i < s.size() && s[i] != '"') {
        if (s[i] == '\\' && i + 1 < s.size()) {
            ++i;
        }
        out.push_back(s[i]);
        ++i;
    }
    if (i >= s.size()) {
        return false;
    }
    ++i;
    return true;
}

bool parseNumber(std::string_view s, std::size_t& i, double& out) {
    skipWs(s, i);
    std::size_t start = i;
    if (i < s.size() && (s[i] == '-' || s[i] == '+')) {
        ++i;
    }
    bool any = false;
    while (i < s.size() && (std::isdigit(static_cast<unsigned char>(s[i])) || s[i] == '.' ||
                            s[i] == 'e' || s[i] == 'E' || s[i] == '+' || s[i] == '-')) {
        any = true;
        ++i;
    }
    if (!any) {
        return false;
    }
    try {
        out = std::stod(std::string(s.substr(start, i - start)));
    } catch (...) {
        return false;
    }
    return std::isfinite(out) || true;  // allow inf/nan strings separately
}

int sourceFromName(const std::string& n) {
    if (n == "simulator") return static_cast<int>(MessageSource::Simulator);
    if (n == "replay") return static_cast<int>(MessageSource::Replay);
    if (n == "test") return static_cast<int>(MessageSource::TestFixture);
    return static_cast<int>(MessageSource::Unknown);
}

std::string sourceName(MessageSource s) {
    switch (s) {
        case MessageSource::Simulator:
            return "simulator";
        case MessageSource::Replay:
            return "replay";
        case MessageSource::TestFixture:
            return "test";
        default:
            return "unknown";
    }
}

int qualityFromName(const std::string& n) {
    if (n == "low") return static_cast<int>(SourceQuality::Low);
    if (n == "high") return static_cast<int>(SourceQuality::High);
    if (n == "medium") return static_cast<int>(SourceQuality::Medium);
    return static_cast<int>(SourceQuality::Unknown);
}

std::string qualityName(SourceQuality q) {
    switch (q) {
        case SourceQuality::Low:
            return "low";
        case SourceQuality::High:
            return "high";
        case SourceQuality::Medium:
            return "medium";
        default:
            return "unknown";
    }
}

int secFromName(const std::string& n) {
    if (n == "untrusted") return static_cast<int>(SecurityStatus::Untrusted);
    if (n == "invalid") return static_cast<int>(SecurityStatus::Invalid);
    if (n == "rejected") return static_cast<int>(SecurityStatus::Rejected);
    if (n == "authenticated") return static_cast<int>(SecurityStatus::Authenticated);
    if (n == "validated") return static_cast<int>(SecurityStatus::Validated);
    return static_cast<int>(SecurityStatus::Unverified);
}

std::string secName(SecurityStatus s) {
    switch (s) {
        case SecurityStatus::Untrusted:
            return "untrusted";
        case SecurityStatus::Invalid:
            return "invalid";
        case SecurityStatus::Rejected:
            return "rejected";
        case SecurityStatus::Authenticated:
            return "authenticated";
        case SecurityStatus::Validated:
            return "validated";
        default:
            return "unverified";
    }
}

}  // namespace

bool parseNormalizedJson(std::string_view json, NormalizedV2XMessage& out, std::string& error) {
    out = NormalizedV2XMessage{};
    std::size_t i = 0;
    skipWs(json, i);
    if (i >= json.size() || json[i] != '{') {
        error = "not_object";
        return false;
    }
    ++i;
    while (i < json.size()) {
        skipWs(json, i);
        if (i < json.size() && json[i] == '}') {
            return true;
        }
        std::string key;
        if (!parseString(json, i, key)) {
            error = "bad_key";
            return false;
        }
        skipWs(json, i);
        if (i >= json.size() || json[i] != ':') {
            error = "missing_colon";
            return false;
        }
        ++i;
        skipWs(json, i);
        if (i < json.size() && json[i] == '"') {
            std::string val;
            if (!parseString(json, i, val)) {
                error = "bad_string";
                return false;
            }
            if (key == "vehicle_id") out.vehicle_id = val;
            else if (key == "source") out.source = static_cast<MessageSource>(sourceFromName(val));
            else if (key == "quality") out.quality = static_cast<SourceQuality>(qualityFromName(val));
            else if (key == "security")
                out.declared_security = static_cast<SecurityStatus>(secFromName(val));
            else if (key == "message_type") {
                out.message_type = (val == "bsm_like") ? MessageType::BsmLike : MessageType::CamLike;
            }
        } else if (i < json.size() && (json[i] == 't' || json[i] == 'f' || json[i] == 'n')) {
            if (json.substr(i, 4) == "true") {
                i += 4;
                if (key == "has_explicit_relative") out.has_explicit_relative = true;
            } else if (json.substr(i, 5) == "false") {
                i += 5;
            } else if (json.substr(i, 4) == "null") {
                i += 4;
            } else {
                error = "bad_literal";
                return false;
            }
        } else {
            double n = 0.0;
            if (!parseNumber(json, i, n)) {
                error = "bad_number:" + key;
                return false;
            }
            if (key == "sender_time_s") out.time.sender_time_s = n;
            else if (key == "receive_time_s") out.time.receive_time_s = n;
            else if (key == "clock_offset_s") out.time.clock_offset_s = n;
            else if (key == "latitude_deg") out.geo.latitude_deg = n;
            else if (key == "longitude_deg") out.geo.longitude_deg = n;
            else if (key == "altitude_m") out.geo.altitude_m = n;
            else if (key == "ve_mps") out.velocity_enu.east_m = n;
            else if (key == "vn_mps") out.velocity_enu.north_m = n;
            else if (key == "vu_mps") out.velocity_enu.up_m = n;
            else if (key == "ae_mps2") out.acceleration_enu.east_m = n;
            else if (key == "an_mps2") out.acceleration_enu.north_m = n;
            else if (key == "au_mps2") out.acceleration_enu.up_m = n;
            else if (key == "heading_rad") out.heading_rad = n;
            else if (key == "yaw_rate_rps") out.yaw_rate_rps = n;
            else if (key == "length_m") {
                out.dimensions.length_m = n;
                out.dimensions.valid = true;
            } else if (key == "width_m")
                out.dimensions.width_m = n;
            else if (key == "declared_pos_std_m")
                out.declared_pos_std_m = n;
            else if (key == "declared_vel_std_mps")
                out.declared_vel_std_mps = n;
            else if (key == "rel_e_m")
                out.relative_enu.east_m = n;
            else if (key == "rel_n_m")
                out.relative_enu.north_m = n;
            else if (key == "relative_std_m")
                out.relative_std_m = n;
        }
        skipWs(json, i);
        if (i < json.size() && json[i] == ',') {
            ++i;
            continue;
        }
        if (i < json.size() && json[i] == '}') {
            return true;
        }
        error = "bad_separator";
        return false;
    }
    error = "unterminated";
    return false;
}

std::string serializeNormalizedJson(const NormalizedV2XMessage& msg) {
    std::ostringstream o;
    o.setf(std::ios::fmtflags(0), std::ios::floatfield);
    o << "{"
      << "\"vehicle_id\":\"" << msg.vehicle_id << "\","
      << "\"sender_time_s\":" << msg.time.sender_time_s << ","
      << "\"receive_time_s\":" << msg.time.receive_time_s << ","
      << "\"clock_offset_s\":" << msg.time.clock_offset_s << ","
      << "\"latitude_deg\":" << msg.geo.latitude_deg << ","
      << "\"longitude_deg\":" << msg.geo.longitude_deg << ","
      << "\"altitude_m\":" << msg.geo.altitude_m << ","
      << "\"ve_mps\":" << msg.velocity_enu.east_m << ","
      << "\"vn_mps\":" << msg.velocity_enu.north_m << ","
      << "\"vu_mps\":" << msg.velocity_enu.up_m << ","
      << "\"ae_mps2\":" << msg.acceleration_enu.east_m << ","
      << "\"an_mps2\":" << msg.acceleration_enu.north_m << ","
      << "\"au_mps2\":" << msg.acceleration_enu.up_m << ","
      << "\"heading_rad\":" << msg.heading_rad << ","
      << "\"yaw_rate_rps\":" << msg.yaw_rate_rps << ","
      << "\"length_m\":" << msg.dimensions.length_m << ","
      << "\"width_m\":" << msg.dimensions.width_m << ","
      << "\"message_type\":\"cam_like\","
      << "\"source\":\"" << sourceName(msg.source) << "\","
      << "\"quality\":\"" << qualityName(msg.quality) << "\","
      << "\"security\":\"" << secName(msg.declared_security) << "\","
      << "\"declared_pos_std_m\":" << msg.declared_pos_std_m << ","
      << "\"declared_vel_std_mps\":" << msg.declared_vel_std_mps << ","
      << "\"has_explicit_relative\":" << (msg.has_explicit_relative ? "true" : "false")
      << "}";
    return o.str();
}

void InMemoryV2XTransport::push(NormalizedV2XMessage msg) {
    queued_.push_back(std::move(msg));
}

std::vector<NormalizedV2XMessage> InMemoryV2XTransport::poll(double) {
    auto out = queued_;
    queued_.clear();
    return out;
}

double SimulatedV2XTransport::nextRand() {
    rng_ = rng_ * 6364136223846793005ULL + 1ULL;
    return static_cast<double>(rng_ >> 11) / static_cast<double>(1ULL << 53);
}

SimulatedV2XTransport::SimulatedV2XTransport(SimulatedV2XConfig cfg) : cfg_(std::move(cfg)) {
    rng_ = cfg_.seed ? cfg_.seed : 1U;
}

std::vector<NormalizedV2XMessage> SimulatedV2XTransport::poll(double now_s) {
    std::vector<NormalizedV2XMessage> out;
    if (now_s + 1e-12 < last_emit_s_ + cfg_.dt_s && last_emit_s_ >= 0.0) {
        return out;
    }
    last_emit_s_ = now_s;
    EnuOrigin origin{cfg_.origin_lat_deg, cfg_.origin_lon_deg, 920.0, true};
    for (const auto& v : cfg_.remotes) {
        if (nextRand() < cfg_.packet_loss) {
            continue;
        }
        const double t = std::max(now_s, 0.0);
        const double dist = v.speed_mps * t;
        double ve = 0.0;
        double vn = 0.0;
        headingSpeedToEnu(v.heading_rad + v.yaw_rate_rps * t, v.speed_mps, ve, vn);
        EnuVector pos{ve * t, vn * t, 0.0};
        // Offset each remote from origin using its lat0/lon0 as an ENU start if provided.
        const GeoPosition start{v.lat0_deg != 0.0 ? v.lat0_deg : cfg_.origin_lat_deg,
                                v.lon0_deg != 0.0 ? v.lon0_deg : cfg_.origin_lon_deg, 920.0};
        EnuVector base = geoToLocalENU(start, origin);
        pos.east_m += base.east_m;
        pos.north_m += base.north_m;
        pos.east_m += cfg_.remote_gps_bias_m;
        const double n1 = (nextRand() * 2.0 - 1.0) * v.pos_std_m;
        const double n2 = (nextRand() * 2.0 - 1.0) * v.pos_std_m;
        pos.east_m += n1;
        pos.north_m += n2;
        (void)dist;
        GeoPosition geo = localENUToGeo(pos, origin);
        NormalizedV2XMessage m{};
        m.vehicle_id = v.id;
        m.time.sender_time_s = now_s - cfg_.latency_s + (nextRand() * 2.0 - 1.0) * cfg_.jitter_s -
                               cfg_.timestamp_error_s;
        m.time.receive_time_s = now_s;
        if (nextRand() < cfg_.out_of_order_rate) {
            m.time.sender_time_s -= 1.0;
        }
        m.geo = geo;
        m.velocity_enu = {ve + (nextRand() * 2.0 - 1.0) * cfg_.velocity_std_mps,
                          vn + (nextRand() * 2.0 - 1.0) * cfg_.velocity_std_mps, 0.0};
        m.heading_rad = v.heading_rad + v.yaw_rate_rps * t;
        m.yaw_rate_rps = v.yaw_rate_rps;
        m.message_type = MessageType::CamLike;
        m.source = MessageSource::Simulator;
        m.quality = SourceQuality::Medium;
        m.declared_security = SecurityStatus::Unverified;
        m.declared_pos_std_m = v.pos_std_m;
        m.declared_vel_std_mps = cfg_.velocity_std_mps;
        if (nextRand() < cfg_.bad_message_rate) {
            m.geo.latitude_deg = 1.0e9;
        }
        out.push_back(m);
        if (nextRand() < cfg_.duplicate_rate) {
            out.push_back(m);
        }
    }
    return out;
}

ReplayV2XTransport::ReplayV2XTransport(std::string jsonl_path) {
    std::ifstream in(jsonl_path);
    loaded_ = static_cast<bool>(in);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }
        NormalizedV2XMessage msg;
        std::string err;
        if (parseNormalizedJson(line, msg, err)) {
            if (msg.source == MessageSource::Unknown) {
                msg.source = MessageSource::Replay;
            }
            messages_.push_back(std::move(msg));
        }
    }
}

std::vector<NormalizedV2XMessage> ReplayV2XTransport::poll(double now_s) {
    std::vector<NormalizedV2XMessage> out;
    while (index_ < messages_.size() && messages_[index_].time.receive_time_s <= now_s + 1e-9) {
        out.push_back(messages_[index_]);
        ++index_;
    }
    return out;
}

std::unique_ptr<IV2XTransport> makeSimulatedTransport(const SimulatedV2XConfig& cfg) {
    return std::make_unique<SimulatedV2XTransport>(cfg);
}

std::unique_ptr<IV2XTransport> makeReplayTransport(const std::string& path) {
    return std::make_unique<ReplayV2XTransport>(path);
}

}  // namespace sih26168::v2x
