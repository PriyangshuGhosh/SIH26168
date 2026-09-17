#pragma once

#include <cstdint>

namespace sih26168::member4 {

/* Authoritative Member 4 output contract (also mirrored under member5). */
struct MapMatchedPosition {
    double timestamp{0.0};
    double lat_snapped{0.0};
    double lon_snapped{0.0};
    double heading_snapped_rad{0.0};
    std::int64_t road_segment_id{0};
    double confidence_score{0.0};
    bool is_on_road_network{false};
};

}  // namespace sih26168::member4
