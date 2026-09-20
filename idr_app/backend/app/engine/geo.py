from __future__ import annotations

import math

MAX_VEHICLE_SPEED_MPS = 55.0  # ~198 km/h
MIN_VARIANCE = 1e-6
MAX_SEARCH_RADIUS_M = 120.0
SPEED_JUMP_MPS = 12.0


def mps_to_kmh(mps: float) -> float:
    return mps * 3.6


def speed_display(speed_mps: float, valid: bool) -> str:
    if not valid or not math.isfinite(speed_mps):
        return "Speed unavailable"
    return f"{mps_to_kmh(speed_mps):.1f} km/h"


def heading_from_east_ccw_rad(yaw: float) -> float:
    """Convert math yaw (0 = east, CCW) to compass heading degrees (0 = north, CW)."""
    deg = (90.0 - math.degrees(yaw)) % 360.0
    return deg


def wrap_angle(rad: float) -> float:
    return (rad + math.pi) % (2.0 * math.pi) - math.pi


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6378137.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


class LocalTangent:
    def __init__(self, lat0: float, lon0: float) -> None:
        self.lat0 = lat0
        self.lon0 = lon0
        self._r = 6378137.0
        self._clat = math.cos(math.radians(lat0))

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        x = math.radians(lon - self.lon0) * self._r * self._clat
        y = math.radians(lat - self.lat0) * self._r
        return x, y

    def to_ll(self, x: float, y: float) -> tuple[float, float]:
        lat = self.lat0 + math.degrees(y / self._r)
        lon = self.lon0 + math.degrees(x / (self._r * self._clat))
        return lat, lon
