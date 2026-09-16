#pragma once

#include "member5/fusion_types.h"
#include "member5/map_matching_types.h"

#include <string>

namespace sih26168::member5 {

/* Pass-through matcher until Member 4 lands. Path prefix "synthetic:" enables
   a north-south corridor snap used by the Member 5 end-to-end harness. */
class StubMapMatcher {
public:
    bool loadMap(const char* map_db_path);

    sih26168::member4::MapMatchedPosition match(const sih26168::member3::NavigationState& nav) const;

    const std::string& mapPath() const { return map_path_; }

private:
    std::string map_path_;
    bool have_map_{false};
    bool synthetic_ns_road_{false};
    double road_lon_{77.5946};
};

}  // namespace sih26168::member5
