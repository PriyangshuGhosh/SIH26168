#pragma once

#include "sih26168/v2x/config.hpp"
#include "sih26168/v2x/frames.hpp"
#include "sih26168/v2x/types.hpp"

#include <string>
#include <vector>

namespace sih26168::v2x {

struct RelativeSnapshot {
    double time_s{0.0};
    EnuVector r_enu{};          // remote - ego at last GNSS-available epoch
    EnuVector v_rel_enu{};
    double cov_m2{25.0};
    bool valid{false};
};

struct RemoteTrack {
    RemoteVehicleState state{};
    double last_sender_time_s{-1.0};
    GeoPosition last_geo{};
    bool have_geo{false};
    RelativeSnapshot relative{};
    std::uint64_t updates{0};
};

GateDecision shouldUseMeasurement(const LocalNavigationState& local, const EnuOrigin& origin,
                                  const CooperativeMeasurement& meas, const V2XConfig& cfg,
                                  double& nis, std::string& reason);

double mahalanobis2(double dn, double de, const std::array<std::array<double, 2>, 2>& s_ne);

CooperativeMeasurement fuseTracks(const std::vector<RemoteTrack>& tracks,
                                  const LocalNavigationState& local, const EnuOrigin& origin,
                                  const V2XConfig& cfg);

void updateRelativeSnapshot(RemoteTrack& track, const LocalNavigationState& local,
                            const EnuOrigin& origin, const V2XConfig& cfg);

}  // namespace sih26168::v2x
