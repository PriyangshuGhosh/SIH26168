"""Local metric projection helpers for WGS84 road geometry."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt

from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform


@dataclass(frozen=True)
class RoadProjection:
    projected_latitude: float
    projected_longitude: float
    distance_m: float
    fraction_along: float


def _local_transformers(latitude: float, longitude: float):
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} "
        "+datum=WGS84 +units=m +no_defs"
    )
    to_local = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True).transform
    to_wgs84 = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True).transform
    return to_local, to_wgs84


def project_point_to_road(
    latitude: float,
    longitude: float,
    road_geometry: LineString,
) -> RoadProjection:
    """Project a GPS point onto a road LineString; distance in metres."""
    to_local, to_wgs84 = _local_transformers(latitude, longitude)
    vehicle_local = transform(to_local, Point(longitude, latitude))
    road_local = transform(to_local, road_geometry)
    length = max(road_local.length, 1e-9)
    along = road_local.project(vehicle_local)
    projected_local = road_local.interpolate(along)
    projected_wgs84 = transform(to_wgs84, projected_local)
    return RoadProjection(
        projected_latitude=projected_wgs84.y,
        projected_longitude=projected_wgs84.x,
        distance_m=float(vehicle_local.distance(projected_local)),
        fraction_along=float(along / length),
    )


def haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def bearing_rad(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing in radians: 0 = north, +pi/2 = east."""
    p1, p2 = radians(lat1), radians(lat2)
    dl = radians(lon2 - lon1)
    y = sin(dl) * cos(p2)
    x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return atan2(y, x) % (2 * 3.141592653589793)


def angular_difference_rad(a: float, b: float) -> float:
    """Smallest absolute angle difference in [0, pi]."""
    d = (a - b + 3.141592653589793) % (2 * 3.141592653589793) - 3.141592653589793
    return abs(d)


def meters_to_deg_bbox(
    latitude: float,
    longitude: float,
    radius_m: float,
) -> tuple[float, float, float, float]:
    lat_delta = radius_m / 111_320.0
    lon_delta = radius_m / (111_320.0 * max(cos(radians(latitude)), 1e-6))
    return (
        longitude - lon_delta,
        latitude - lat_delta,
        longitude + lon_delta,
        latitude + lat_delta,
    )
