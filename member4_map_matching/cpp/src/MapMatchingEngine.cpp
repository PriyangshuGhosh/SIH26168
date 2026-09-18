#include "member4/MapMatchingEngine.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <queue>
#include <sstream>
#include <unordered_map>

namespace sih26168::member4 {
namespace {

constexpr double kPi = 3.14159265358979323846;
constexpr double kEarthR = 6371000.0;

}  // namespace

MapMatchingEngine::MapMatchingEngine(MapMatcherConfig config)
    : config_(std::move(config)) {}

bool MapMatchingEngine::loadRoadpack(const std::string& path) {
    last_error_.clear();
    segments_.clear();
    nodes_.clear();
    adj_.clear();
    reset();

    std::ifstream in(path);
    if (!in) {
        last_error_ = "failed to open roadpack: " + path;
        return false;
    }

    std::string line;
    if (!std::getline(in, line) || line != "SIH26168_ROADPACK_V1") {
        last_error_ = "invalid roadpack header";
        return false;
    }

    std::unordered_map<int, int> node_remap;
    int next_node = 0;

    auto ensure_node = [&](int raw_id, double lat, double lon) {
        if (!node_remap.count(raw_id)) {
            node_remap[raw_id] = next_node++;
            nodes_.push_back(Node{lat, lon});
        } else {
            nodes_[node_remap[raw_id]] = Node{lat, lon};
        }
        return node_remap[raw_id];
    };

    while (std::getline(in, line)) {
        if (line.empty()) {
            continue;
        }
        std::istringstream ss(line);
        std::string tag;
        ss >> tag;
        if (tag == "NODE") {
            int id;
            double lat, lon;
            ss >> id >> lat >> lon;
            ensure_node(id, lat, lon);
        } else if (tag == "SEG") {
            Segment seg;
            int n_pts = 0;
            int u_raw = 0;
            int v_raw = 0;
            ss >> seg.id >> u_raw >> v_raw >> seg.length_m >> seg.heading_rad >> n_pts;
            if (!std::getline(in, line)) {
                last_error_ = "truncated segment label";
                return false;
            }
            if (line.rfind("LABEL ", 0) == 0) {
                seg.label = line.substr(6);
            }
            seg.lats.reserve(n_pts);
            seg.lons.reserve(n_pts);
            for (int i = 0; i < n_pts; ++i) {
                if (!std::getline(in, line)) {
                    last_error_ = "truncated segment points";
                    return false;
                }
                std::istringstream ps(line);
                std::string ptag;
                double lat, lon;
                ps >> ptag >> lat >> lon;
                seg.lats.push_back(lat);
                seg.lons.push_back(lon);
            }
            if (seg.lats.empty()) {
                last_error_ = "empty segment geometry";
                return false;
            }
            seg.min_lat = *std::min_element(seg.lats.begin(), seg.lats.end());
            seg.max_lat = *std::max_element(seg.lats.begin(), seg.lats.end());
            seg.min_lon = *std::min_element(seg.lons.begin(), seg.lons.end());
            seg.max_lon = *std::max_element(seg.lons.begin(), seg.lons.end());

            if (!node_remap.count(u_raw)) {
                ensure_node(u_raw, seg.lats.front(), seg.lons.front());
            }
            if (!node_remap.count(v_raw)) {
                ensure_node(v_raw, seg.lats.back(), seg.lons.back());
            }
            seg.u = node_remap[u_raw];
            seg.v = node_remap[v_raw];
            segments_.push_back(std::move(seg));
        }
    }

    adj_.assign(nodes_.size(), {});
    for (std::size_t i = 0; i < segments_.size(); ++i) {
        const auto& s = segments_[i];
        if (s.u >= 0 && s.v >= 0 &&
            static_cast<std::size_t>(s.u) < adj_.size() &&
            static_cast<std::size_t>(s.v) < adj_.size()) {
            adj_[s.u].emplace_back(s.v, s.length_m, static_cast<int>(i));
        }
    }
    return !segments_.empty();
}

void MapMatchingEngine::reset() {
    window_states_.clear();
    window_candidates_.clear();
}

double MapMatchingEngine::positionSigma(const member3::NavigationState& nav) {
    const double c00 = nav.position_cov_m2[0][0];
    const double c11 = nav.position_cov_m2[1][1];
    return std::max(std::sqrt(std::max({c00, c11, 0.0})), 1e-3);
}

double MapMatchingEngine::haversineM(
    double lat1, double lon1, double lat2, double lon2) {
    const double p1 = lat1 * kPi / 180.0;
    const double p2 = lat2 * kPi / 180.0;
    const double dp = (lat2 - lat1) * kPi / 180.0;
    const double dl = (lon2 - lon1) * kPi / 180.0;
    const double a =
        std::sin(dp / 2) * std::sin(dp / 2) +
        std::cos(p1) * std::cos(p2) * std::sin(dl / 2) * std::sin(dl / 2);
    return 2 * kEarthR * std::atan2(std::sqrt(a), std::sqrt(1 - a));
}

double MapMatchingEngine::angularDiff(double a, double b) {
    double d = std::fmod(a - b + kPi, 2 * kPi);
    if (d < 0) {
        d += 2 * kPi;
    }
    return std::abs(d - kPi);
}

double MapMatchingEngine::searchRadius(
    const member3::NavigationState& nav, double base) {
    return std::min(120.0, std::max(base, 3.0 * positionSigma(nav)));
}

void MapMatchingEngine::projectPointToSegment(
    double lat,
    double lon,
    const Segment& seg,
    double& out_lat,
    double& out_lon,
    double& out_dist_m) const {
    // Local ENU metres about the query point.
    const double cos_lat = std::max(std::cos(lat * kPi / 180.0), 1e-6);
    const double m_per_deg_lat = 111320.0;
    const double m_per_deg_lon = 111320.0 * cos_lat;

    auto to_xy = [&](double la, double lo, double& x, double& y) {
        x = (lo - lon) * m_per_deg_lon;
        y = (la - lat) * m_per_deg_lat;
    };

    double best_d2 = std::numeric_limits<double>::infinity();
    double best_x = 0.0;
    double best_y = 0.0;

    for (std::size_t i = 0; i + 1 < seg.lats.size(); ++i) {
        double ax, ay, bx, by;
        to_xy(seg.lats[i], seg.lons[i], ax, ay);
        to_xy(seg.lats[i + 1], seg.lons[i + 1], bx, by);
        const double abx = bx - ax;
        const double aby = by - ay;
        const double apx = 0.0 - ax;
        const double apy = 0.0 - ay;
        const double ab2 = abx * abx + aby * aby;
        double t = 0.0;
        if (ab2 > 1e-12) {
            t = (apx * abx + apy * aby) / ab2;
            t = std::clamp(t, 0.0, 1.0);
        }
        const double px = ax + t * abx;
        const double py = ay + t * aby;
        const double d2 = px * px + py * py;
        if (d2 < best_d2) {
            best_d2 = d2;
            best_x = px;
            best_y = py;
        }
    }

    out_dist_m = std::sqrt(best_d2);
    out_lat = lat + best_y / m_per_deg_lat;
    out_lon = lon + best_x / m_per_deg_lon;
}

std::vector<MapMatchingEngine::Candidate> MapMatchingEngine::generateCandidates(
    const member3::NavigationState& nav) const {
    const double radius = searchRadius(nav, config_.base_search_radius_m);
    const double lat_delta = radius / 111320.0;
    const double lon_delta =
        radius / (111320.0 * std::max(std::cos(nav.latitude * kPi / 180.0), 1e-6));
    const double min_lat = nav.latitude - lat_delta;
    const double max_lat = nav.latitude + lat_delta;
    const double min_lon = nav.longitude - lon_delta;
    const double max_lon = nav.longitude + lon_delta;

    std::vector<Candidate> out;
    for (const auto& seg : segments_) {
        if (seg.max_lon < min_lon || seg.min_lon > max_lon ||
            seg.max_lat < min_lat || seg.min_lat > max_lat) {
            continue;
        }
        Candidate c;
        c.segment_id = seg.id;
        c.u = seg.u;
        c.v = seg.v;
        c.length_m = seg.length_m;
        c.heading_rad = seg.heading_rad;
        projectPointToSegment(
            nav.latitude, nav.longitude, seg, c.lat, c.lon, c.distance_m);
        if (c.distance_m <= radius) {
            out.push_back(c);
        }
    }
    std::sort(out.begin(), out.end(), [](const Candidate& a, const Candidate& b) {
        return a.distance_m < b.distance_m;
    });
    if (out.size() > config_.max_candidates) {
        out.resize(config_.max_candidates);
    }
    return out;
}

double MapMatchingEngine::emissionLog(
    const member3::NavigationState& nav,
    const Candidate& c) const {
    const double sigma = positionSigma(nav);
    const double pos = -0.5 * std::pow(c.distance_m / sigma, 2.0);
    const double heading_sigma = 30.0 * kPi / 180.0;
    const double err_fwd = angularDiff(nav.yaw_rad, c.heading_rad);
    const double err_rev = angularDiff(nav.yaw_rad, c.heading_rad + kPi);
    double heading_err = err_fwd;
    double reverse_penalty = 0.0;
    if (err_rev < err_fwd) {
        heading_err = err_rev;
        reverse_penalty = 1.5;
    }
    const double hdg =
        -0.5 * std::pow(heading_err / heading_sigma, 2.0) - reverse_penalty;
    return pos + hdg;
}

double MapMatchingEngine::networkDistanceM(
    const Candidate& prev,
    const Candidate& cur,
    double observed_m) const {
    if (prev.segment_id == cur.segment_id || prev.v == cur.u) {
        return std::max(observed_m, 0.0);
    }
    if (prev.v < 0 || cur.u < 0 ||
        static_cast<std::size_t>(prev.v) >= adj_.size()) {
        return std::numeric_limits<double>::infinity();
    }

    // Dijkstra from prev.v to cur.u
    const double inf = std::numeric_limits<double>::infinity();
    std::vector<double> dist(nodes_.size(), inf);
    using NodeDist = std::pair<double, int>;
    std::priority_queue<NodeDist, std::vector<NodeDist>, std::greater<NodeDist>> pq;
    dist[prev.v] = 0.0;
    pq.push({0.0, prev.v});
    while (!pq.empty()) {
        const auto [d, u] = pq.top();
        pq.pop();
        if (d > dist[u]) {
            continue;
        }
        if (u == cur.u) {
            break;
        }
        for (const auto& [v, w, /*seg*/ _] : adj_[u]) {
            const double nd = d + w;
            if (nd < dist[v]) {
                dist[v] = nd;
                pq.push({nd, v});
            }
        }
    }
    return dist[cur.u];
}

double MapMatchingEngine::transitionLog(
    const member3::NavigationState& prev_nav,
    const member3::NavigationState& cur_nav,
    const Candidate& prev,
    const Candidate& cur) const {
    const double observed = haversineM(
        prev_nav.latitude, prev_nav.longitude, cur_nav.latitude, cur_nav.longitude);
    const double net = networkDistanceM(prev, cur, observed);
    if (!std::isfinite(net)) {
        return -std::numeric_limits<double>::infinity();
    }
    const double sigma_t = 25.0;
    const double dist_score = -0.5 * std::pow((net - observed) / sigma_t, 2.0);
    const double road_turn = angularDiff(prev.heading_rad, cur.heading_rad);
    const double yaw_turn = angularDiff(prev_nav.yaw_rad, cur_nav.yaw_rad);
    const double turn_sigma = 45.0 * kPi / 180.0;
    const double turn_score =
        -0.5 * std::pow((road_turn - yaw_turn) / turn_sigma, 2.0);
    return dist_score + 0.25 * turn_score;
}

std::vector<MapMatchingEngine::Candidate> MapMatchingEngine::viterbi(
    const std::vector<member3::NavigationState>& states,
    const std::vector<std::vector<Candidate>>& cand_sets) const {
    const std::size_t n = states.size();
    std::vector<Candidate> path(n);
    std::vector<char> has(n, 0);

    std::vector<std::vector<double>> scores(n);
    std::vector<std::vector<int>> back(n);

    for (std::size_t t = 0; t < n; ++t) {
        const auto& cands = cand_sets[t];
        if (cands.empty()) {
            continue;
        }
        scores[t].assign(cands.size(), -std::numeric_limits<double>::infinity());
        back[t].assign(cands.size(), -1);
        if (t == 0 || scores[t - 1].empty()) {
            for (std::size_t i = 0; i < cands.size(); ++i) {
                scores[t][i] = emissionLog(states[t], cands[i]);
            }
        } else {
            for (std::size_t i = 0; i < cands.size(); ++i) {
                const double emit = emissionLog(states[t], cands[i]);
                double best = -std::numeric_limits<double>::infinity();
                int best_j = -1;
                for (std::size_t j = 0; j < cand_sets[t - 1].size(); ++j) {
                    const double score =
                        scores[t - 1][j] +
                        transitionLog(
                            states[t - 1], states[t], cand_sets[t - 1][j], cands[i]) +
                        emit;
                    if (score > best) {
                        best = score;
                        best_j = static_cast<int>(j);
                    }
                }
                scores[t][i] = best;
                back[t][i] = best_j;
            }
        }
    }

    for (int t = static_cast<int>(n) - 1; t >= 0;) {
        if (scores[t].empty()) {
            --t;
            continue;
        }
        int start = t;
        while (start > 0 && !scores[start - 1].empty()) {
            --start;
        }
        int best_i = 0;
        for (std::size_t i = 1; i < scores[t].size(); ++i) {
            if (scores[t][i] > scores[t][best_i]) {
                best_i = static_cast<int>(i);
            }
        }
        for (int k = t; k >= start; --k) {
            path[k] = cand_sets[k][best_i];
            has[k] = 1;
            best_i = back[k][best_i];
            if (best_i < 0) {
                break;
            }
        }
        t = start - 1;
    }

    std::vector<Candidate> out;
    out.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (has[i]) {
            out.push_back(path[i]);
        } else {
            out.push_back(Candidate{});
        }
    }
    // Encode missing via segment_id==0 and empty cand set checked by caller
    for (std::size_t i = 0; i < n; ++i) {
        if (!has[i]) {
            out[i].segment_id = 0;
            out[i].distance_m = -1.0;
        }
    }
    return out;
}

MapMatchedPosition MapMatchingEngine::toOutput(
    const member3::NavigationState& nav,
    const Candidate* matched,
    const std::vector<Candidate>& candidates) const {
    MapMatchedPosition m;
    m.timestamp = nav.timestamp;
    if (matched == nullptr || matched->distance_m < 0.0 || matched->segment_id == 0) {
        m.lat_snapped = nav.latitude;
        m.lon_snapped = nav.longitude;
        m.heading_snapped_rad = nav.yaw_rad;
        m.road_segment_id = 0;
        m.confidence_score = 0.0;
        m.is_on_road_network = false;
        return m;
    }

    // Softmax over emissions
    double max_s = -std::numeric_limits<double>::infinity();
    std::vector<double> scores;
    scores.reserve(candidates.size());
    for (const auto& c : candidates) {
        const double s = emissionLog(nav, c);
        scores.push_back(s);
        max_s = std::max(max_s, s);
    }
    double sum = 0.0;
    for (double s : scores) {
        sum += std::exp(s - max_s);
    }
    const double matched_s = emissionLog(nav, *matched);
    double confidence = (sum > 0.0) ? std::exp(matched_s - max_s) / sum : 0.0;
    const double sigma = positionSigma(nav);
    if (sigma > 10.0) {
        confidence *= 10.0 / sigma;
    }

    const bool on_road =
        confidence >= config_.on_road_confidence_min &&
        matched->distance_m <= config_.on_road_distance_max_m &&
        sigma <= config_.max_sigma_for_forced_on_road_m;

    m.road_segment_id = matched->segment_id;
    m.confidence_score = confidence;
    if (on_road) {
        m.lat_snapped = matched->lat;
        m.lon_snapped = matched->lon;
        m.heading_snapped_rad = matched->heading_rad;
        m.is_on_road_network = true;
    } else {
        m.lat_snapped = nav.latitude;
        m.lon_snapped = nav.longitude;
        m.heading_snapped_rad = nav.yaw_rad;
        m.is_on_road_network = false;
    }
    return m;
}

MapMatchedPosition MapMatchingEngine::match(const member3::NavigationState& nav) {
    if (segments_.empty()) {
        MapMatchedPosition m;
        m.timestamp = nav.timestamp;
        m.lat_snapped = nav.latitude;
        m.lon_snapped = nav.longitude;
        m.heading_snapped_rad = nav.yaw_rad;
        return m;
    }

    auto cands = generateCandidates(nav);
    window_states_.push_back(nav);
    window_candidates_.push_back(cands);
    if (window_states_.size() > config_.window_size) {
        window_states_.erase(window_states_.begin());
        window_candidates_.erase(window_candidates_.begin());
    }

    auto path = viterbi(window_states_, window_candidates_);
    const Candidate* matched = nullptr;
    if (!path.empty() && path.back().distance_m >= 0.0 && path.back().segment_id != 0) {
        matched = &path.back();
    } else if (!cands.empty()) {
        // Should not normally happen; keep fail-safe
        matched = nullptr;
    }
    return toOutput(nav, matched, cands);
}

std::vector<MapMatchedPosition> MapMatchingEngine::matchTrajectory(
    const std::vector<member3::NavigationState>& states) {
    std::vector<std::vector<Candidate>> cand_sets;
    cand_sets.reserve(states.size());
    for (const auto& s : states) {
        cand_sets.push_back(generateCandidates(s));
    }
    auto path = viterbi(states, cand_sets);
    std::vector<MapMatchedPosition> out;
    out.reserve(states.size());
    for (std::size_t i = 0; i < states.size(); ++i) {
        const Candidate* matched = nullptr;
        if (i < path.size() && path[i].distance_m >= 0.0 && path[i].segment_id != 0) {
            matched = &path[i];
        }
        out.push_back(toOutput(states[i], matched, cand_sets[i]));
    }
    return out;
}

}  // namespace sih26168::member4
