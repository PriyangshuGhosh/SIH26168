#pragma once

#include <cstdint>

namespace sih26168::member3 {

enum class NavigationMode : std::int32_t {
    GNSS_AIDED = 0,
    DEAD_RECKONING = 1
};

struct NavigationState {
    double timestamp{0.0};
    double latitude{0.0};
    double longitude{0.0};
    double altitude{0.0};
    double v_x{0.0};
    double v_y{0.0};
    double yaw_rad{0.0};
    double position_cov_m2[2][2]{{0.5, 0.0}, {0.0, 0.5}};
    NavigationMode mode{NavigationMode::DEAD_RECKONING};
};

}  // namespace sih26168::member3
