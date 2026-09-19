#pragma once

#include "sih26168/v2x/types.hpp"

namespace sih26168::v2x {

struct EnuOrigin {
    double latitude_deg{0.0};
    double longitude_deg{0.0};
    double altitude_m{0.0};
    bool valid{false};
};

// WGS84 degrees → local ENU metres. Same spherical approximation as Member 3.
EnuVector geoToLocalENU(const GeoPosition& geo, const EnuOrigin& origin);
GeoPosition localENUToGeo(const EnuVector& enu, const EnuOrigin& origin);

// ENU (east, north) ↔ Member 3 local tangent (north, east).
void enuToMember3NorthEast(const EnuVector& enu, double& north_m, double& east_m);
EnuVector member3NorthEastToEnu(double north_m, double east_m, double up_m = 0.0);

// Member 3 body velocity → ENU using the EKF's published kinematics, not a new model.
void vehicleFrameToNavigationEnu(double v_x, double v_y, double yaw_rad,
                                 double& v_east_mps, double& v_north_mps);

void navigationEnuToVehicleFrame(double v_east_mps, double v_north_mps, double yaw_rad,
                                 double& v_x, double& v_y);

// Heading 0=North, increasing toward East. Speed along heading → ENU velocity.
void headingSpeedToEnu(double heading_rad, double speed_mps, double& v_east, double& v_north);

double wrapPi(double rad);
bool finiteNumber(double x);
bool validLatitude(double lat_deg);
bool validLongitude(double lon_deg);

}  // namespace sih26168::v2x
