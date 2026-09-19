#pragma once

#include <cstdint>

namespace sih26168::member4 {

/* Explicit no-match / coverage states. Never encode these as lat/lon 0,0. */
enum class MatchStatus : int {
    Ok = 0,
    NoMapData = 1,
    OutsideMap = 2,
    NoCandidates = 3,
    Rejected = 4,
    InvalidCoordinates = 5
};

/* Authoritative Member 4 output contract (also mirrored under member5).
   Existing fields keep their original order so Member 5 field copies stay valid.
   Extra fields are appended. */
struct MapMatchedPosition {
    double timestamp{0.0};
    double lat_snapped{0.0};
    double lon_snapped{0.0};
    double heading_snapped_rad{0.0};
    std::int64_t road_segment_id{0};
    double confidence_score{0.0};
    bool is_on_road_network{false};
    double match_distance_m{-1.0};
    bool map_available{false};
    bool match_valid{false};
    MatchStatus match_status{MatchStatus::NoMapData};
};

inline const char* matchStatusCString(MatchStatus s) {
    switch (s) {
        case MatchStatus::Ok:
            return "OK";
        case MatchStatus::NoMapData:
            return "NO_MAP_DATA";
        case MatchStatus::OutsideMap:
            return "OUTSIDE_MAP";
        case MatchStatus::NoCandidates:
            return "NO_CANDIDATES";
        case MatchStatus::Rejected:
            return "REJECTED";
        case MatchStatus::InvalidCoordinates:
            return "INVALID_COORDINATES";
    }
    return "UNKNOWN";
}

}  // namespace sih26168::member4
