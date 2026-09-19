#pragma once

#include "sih26168/v2x/types.hpp"

namespace sih26168::v2x {

// DESIGNED integration seam. This header does not include Member 3 types so the
// V2X library stays independently buildable. Member 3 can later copy fields:
//
//   LocalNavigationState loc;
//   loc.timestamp_s = nav.timestamp;
//   loc.latitude_deg = nav.latitude;
//   loc.longitude_deg = nav.longitude;
//   loc.v_x = nav.v_x;
//   loc.v_y = nav.v_y;
//   loc.yaw_rad = nav.yaw_rad;
//   loc.position_cov_ne = nav.position_cov_m2;
//   loc.gnss_available = (nav.mode == GNSS_AIDED);
//   loc.valid = nav.valid;
//   auto result = core.getCooperativeMeasurement(loc);
//   if (result.decision == GateDecision::Accept ||
//       result.decision == GateDecision::Downweight)
//       ekf.updatePosition(result.measurement.north_m, result.measurement.east_m,
//                          result.measurement.position_cov_ne);
//
// Do not treat CooperativeMeasurement as GNSS. It is optional and may be
// Unavailable when relative geometry is not observable.

struct Member3Hook {
    bool enabled{false};
    const char* status{"DESIGNED_NOT_WIRED"};
};

}  // namespace sih26168::v2x
