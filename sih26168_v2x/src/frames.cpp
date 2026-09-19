#include "sih26168/v2x/frames.hpp"

#include <cmath>
#include <limits>
#include <numbers>

namespace sih26168::v2x {
namespace {

constexpr double kPi = std::numbers::pi;

}  // namespace

bool finiteNumber(double x) {
    return std::isfinite(x);
}

bool validLatitude(double lat_deg) {
    return finiteNumber(lat_deg) && lat_deg >= -90.0 && lat_deg <= 90.0;
}

bool validLongitude(double lon_deg) {
    return finiteNumber(lon_deg) && lon_deg >= -180.0 && lon_deg <= 180.0;
}

double wrapPi(double rad) {
    if (!std::isfinite(rad)) {
        return rad;
    }
    return std::atan2(std::sin(rad), std::cos(rad));
}

EnuVector geoToLocalENU(const GeoPosition& geo, const EnuOrigin& origin) {
    EnuVector enu{};
    if (!origin.valid || !validLatitude(geo.latitude_deg) || !validLongitude(geo.longitude_deg) ||
        !validLatitude(origin.latitude_deg) || !validLongitude(origin.longitude_deg) ||
        !finiteNumber(geo.altitude_m) || !finiteNumber(origin.altitude_m)) {
        return enu;
    }
    const double lat0 = origin.latitude_deg * kPi / 180.0;
    enu.north_m = (geo.latitude_deg - origin.latitude_deg) * kPi / 180.0 * kEarthRadiusM;
    enu.east_m = (geo.longitude_deg - origin.longitude_deg) * kPi / 180.0 * kEarthRadiusM *
                 std::cos(lat0);
    enu.up_m = geo.altitude_m - origin.altitude_m;
    return enu;
}

GeoPosition localENUToGeo(const EnuVector& enu, const EnuOrigin& origin) {
    GeoPosition geo{};
    geo.latitude_deg = origin.latitude_deg;
    geo.longitude_deg = origin.longitude_deg;
    geo.altitude_m = origin.altitude_m;
    if (!origin.valid || !finiteNumber(enu.east_m) || !finiteNumber(enu.north_m) ||
        !finiteNumber(enu.up_m)) {
        return geo;
    }
    const double lat0 = origin.latitude_deg * kPi / 180.0;
    geo.latitude_deg = origin.latitude_deg + enu.north_m / kEarthRadiusM * 180.0 / kPi;
    const double c = std::max(std::abs(std::cos(lat0)), 1e-8);
    geo.longitude_deg = origin.longitude_deg + enu.east_m / (kEarthRadiusM * c) * 180.0 / kPi;
    geo.altitude_m = origin.altitude_m + enu.up_m;
    return geo;
}

void enuToMember3NorthEast(const EnuVector& enu, double& north_m, double& east_m) {
    north_m = enu.north_m;
    east_m = enu.east_m;
}

EnuVector member3NorthEastToEnu(double north_m, double east_m, double up_m) {
    return EnuVector{east_m, north_m, up_m};
}

void vehicleFrameToNavigationEnu(double v_x, double v_y, double yaw_rad, double& v_east_mps,
                                 double& v_north_mps) {
    const double c = std::cos(yaw_rad);
    const double s = std::sin(yaw_rad);
    v_north_mps = v_x * c - v_y * s;
    v_east_mps = v_x * s + v_y * c;
}

void navigationEnuToVehicleFrame(double v_east_mps, double v_north_mps, double yaw_rad, double& v_x,
                                 double& v_y) {
    const double c = std::cos(yaw_rad);
    const double s = std::sin(yaw_rad);
    v_x = v_north_mps * c + v_east_mps * s;
    v_y = -v_north_mps * s + v_east_mps * c;
}

void headingSpeedToEnu(double heading_rad, double speed_mps, double& v_east, double& v_north) {
    v_north = speed_mps * std::cos(heading_rad);
    v_east = speed_mps * std::sin(heading_rad);
}

}  // namespace sih26168::v2x
