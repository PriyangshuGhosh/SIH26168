from __future__ import annotations

import math

from .types import EARTH_RADIUS_M, EnuOrigin, EnuVector, GeoPosition


def finite_number(x: float) -> bool:
    return math.isfinite(x)


def valid_latitude(lat_deg: float) -> bool:
    return finite_number(lat_deg) and -90.0 <= lat_deg <= 90.0


def valid_longitude(lon_deg: float) -> bool:
    return finite_number(lon_deg) and -180.0 <= lon_deg <= 180.0


def wrap_pi(rad: float) -> float:
    if not math.isfinite(rad):
        return rad
    return math.atan2(math.sin(rad), math.cos(rad))


def geo_to_local_enu(geo: GeoPosition, origin: EnuOrigin) -> EnuVector:
    if (
        not origin.valid
        or not valid_latitude(geo.latitude_deg)
        or not valid_longitude(geo.longitude_deg)
        or not valid_latitude(origin.latitude_deg)
        or not valid_longitude(origin.longitude_deg)
        or not finite_number(geo.altitude_m)
        or not finite_number(origin.altitude_m)
    ):
        return EnuVector()
    lat0 = math.radians(origin.latitude_deg)
    north = math.radians(geo.latitude_deg - origin.latitude_deg) * EARTH_RADIUS_M
    east = math.radians(geo.longitude_deg - origin.longitude_deg) * EARTH_RADIUS_M * math.cos(lat0)
    return EnuVector(east_m=east, north_m=north, up_m=geo.altitude_m - origin.altitude_m)


def local_enu_to_geo(enu: EnuVector, origin: EnuOrigin) -> GeoPosition:
    geo = GeoPosition(origin.latitude_deg, origin.longitude_deg, origin.altitude_m)
    if not origin.valid:
        return geo
    lat0 = math.radians(origin.latitude_deg)
    c = max(abs(math.cos(lat0)), 1e-8)
    geo.latitude_deg = origin.latitude_deg + math.degrees(enu.north_m / EARTH_RADIUS_M)
    geo.longitude_deg = origin.longitude_deg + math.degrees(enu.east_m / (EARTH_RADIUS_M * c))
    geo.altitude_m = origin.altitude_m + enu.up_m
    return geo


def enu_to_member3_north_east(enu: EnuVector) -> tuple[float, float]:
    return enu.north_m, enu.east_m


def member3_north_east_to_enu(north_m: float, east_m: float, up_m: float = 0.0) -> EnuVector:
    return EnuVector(east_m=east_m, north_m=north_m, up_m=up_m)


def vehicle_frame_to_navigation_enu(v_x: float, v_y: float, yaw_rad: float) -> tuple[float, float]:
    """Member 3 predict() kinematics: yaw 0 = North, increasing toward East."""
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    v_north = v_x * c - v_y * s
    v_east = v_x * s + v_y * c
    return v_east, v_north


def heading_speed_to_enu(heading_rad: float, speed_mps: float) -> tuple[float, float]:
    v_north = speed_mps * math.cos(heading_rad)
    v_east = speed_mps * math.sin(heading_rad)
    return v_east, v_north
