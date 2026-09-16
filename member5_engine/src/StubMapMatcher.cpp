#include "member5/StubMapMatcher.hpp"

#include <algorithm>
#include <cmath>

namespace sih26168::member5 {

bool StubMapMatcher::loadMap(const char* map_db_path) {
    map_path_ = (map_db_path != nullptr) ? map_db_path : "";
    have_map_ = !map_path_.empty();
    synthetic_ns_road_ = map_path_.rfind("synthetic:", 0) == 0;
    return true;
}

sih26168::member4::MapMatchedPosition StubMapMatcher::match(
    const sih26168::member3::NavigationState& nav) const {
    sih26168::member4::MapMatchedPosition m;
    m.timestamp = nav.timestamp;
    m.lat_snapped = nav.latitude;
    m.lon_snapped = nav.longitude;
    m.heading_snapped_rad = nav.yaw_rad;
    m.road_segment_id = have_map_ ? 123456789 : 0;
    m.confidence_score = have_map_ ? 1.0 : 0.85;
    m.is_on_road_network = have_map_;

    if (synthetic_ns_road_) {
        m.lon_snapped = road_lon_;
        m.heading_snapped_rad = 0.0;
        m.road_segment_id = 424242;
        m.is_on_road_network = true;
        const double dlon_m = (nav.longitude - road_lon_) * 111320.0 *
                              std::cos(nav.latitude * 3.14159265358979323846 / 180.0);
        m.confidence_score = std::max(0.2, 1.0 - std::abs(dlon_m) / 30.0);
    }
    return m;
}

}  // namespace sih26168::member5
