#pragma once

#include "member3/EKFFusionEngine.hpp"
#include "member4/map_matching_types.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace sih26168::member4 {

struct MapMatcherConfig {
    double base_search_radius_m{30.0};
    std::size_t max_candidates{12};
    std::size_t window_size{8};
    double on_road_confidence_min{0.35};
    double on_road_distance_max_m{25.0};
    double max_sigma_for_forced_on_road_m{40.0};
    /* Candidates farther than this are never considered (no city-scale snap). */
    double max_search_radius_m{120.0};
};

class MapMatchingEngine {
public:
    MapMatchingEngine() = default;
    explicit MapMatchingEngine(MapMatcherConfig config);

    /* Load portable .roadpack produced by Python tools (offline, no network). */
    bool loadRoadpack(const std::string& path);

    bool hasMap() const { return !segments_.empty(); }
    std::size_t segmentCount() const { return segments_.size(); }
    bool geographicBounds(double& min_lat, double& max_lat, double& min_lon, double& max_lon) const;
    bool coversLocation(double lat, double lon, double margin_m = 50.0) const;

    void reset();

    MapMatchedPosition match(const member3::NavigationState& nav);

    /* Batch offline decode for tests / evaluation. */
    std::vector<MapMatchedPosition> matchTrajectory(
        const std::vector<member3::NavigationState>& states);

    const std::string& lastError() const { return last_error_; }

private:
    struct Node {
        double lat{0.0};
        double lon{0.0};
    };

    struct Segment {
        std::int64_t id{0};
        int u{-1};
        int v{-1};
        double length_m{0.0};
        double heading_rad{0.0};
        double min_lon{0.0};
        double min_lat{0.0};
        double max_lon{0.0};
        double max_lat{0.0};
        std::vector<double> lats;
        std::vector<double> lons;
        std::string label;
    };

    struct Candidate {
        std::int64_t segment_id{0};
        double lat{0.0};
        double lon{0.0};
        double distance_m{0.0};
        double heading_rad{0.0};
        int u{-1};
        int v{-1};
        double length_m{0.0};
    };

    MapMatcherConfig config_{};
    std::vector<Node> nodes_;
    std::vector<Segment> segments_;
    /* adjacency: u -> list of (v, length, segment_index) */
    std::vector<std::vector<std::tuple<int, double, int>>> adj_;
    std::string last_error_;

    std::vector<member3::NavigationState> window_states_;
    std::vector<std::vector<Candidate>> window_candidates_;

    static double positionSigma(const member3::NavigationState& nav);
    static double haversineM(double lat1, double lon1, double lat2, double lon2);
    static double angularDiff(double a, double b);
    double searchRadius(const member3::NavigationState& nav, double base) const;

    void projectPointToSegment(
        double lat,
        double lon,
        const Segment& seg,
        double& out_lat,
        double& out_lon,
        double& out_dist_m) const;

    std::vector<Candidate> generateCandidates(const member3::NavigationState& nav) const;

    double emissionLog(
        const member3::NavigationState& nav,
        const Candidate& c) const;

    double transitionLog(
        const member3::NavigationState& prev_nav,
        const member3::NavigationState& cur_nav,
        const Candidate& prev,
        const Candidate& cur) const;

    double networkDistanceM(
        const Candidate& prev,
        const Candidate& cur,
        double observed_m) const;

    std::vector<Candidate> viterbi(
        const std::vector<member3::NavigationState>& states,
        const std::vector<std::vector<Candidate>>& cand_sets) const;

    MapMatchedPosition toOutput(
        const member3::NavigationState& nav,
        const Candidate* matched,
        const std::vector<Candidate>& candidates) const;

    MapMatchedPosition passThrough(
        const member3::NavigationState& nav, MatchStatus status) const;
};

}  // namespace sih26168::member4
