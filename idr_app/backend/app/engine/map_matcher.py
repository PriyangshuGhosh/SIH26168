from __future__ import annotations

import math
from dataclasses import dataclass

from .geo import MAX_SEARCH_RADIUS_M, heading_from_east_ccw_rad, wrap_angle
from .types import MapMatchedPosition, MapStatus, NavigationState


@dataclass
class RoadSegment:
    id: int
    name: str
    ax: float
    ay: float
    bx: float
    by: float
    tunnel: bool = False

    def length(self) -> float:
        return math.hypot(self.bx - self.ax, self.by - self.ay)

    def heading_rad(self) -> float:
        return math.atan2(self.by - self.ay, self.bx - self.ax)

    def project(self, x: float, y: float) -> tuple[float, float, float, float]:
        dx, dy = self.bx - self.ax, self.by - self.ay
        L2 = dx * dx + dy * dy or 1e-9
        t = ((x - self.ax) * dx + (y - self.ay) * dy) / L2
        t_cl = min(1.0, max(0.0, t))
        px, py = self.ax + t_cl * dx, self.ay + t_cl * dy
        dist = math.hypot(x - px, y - py)
        return px, py, t_cl, dist


class MapMatcher:
    def __init__(self, segments: list[RoadSegment], origin_ok: callable) -> None:
        self.segments = segments
        self._in_coverage = origin_ok
        self._prev_id: int | None = None
        self._history: list[tuple[int, float]] = []

    def reset(self) -> None:
        self._prev_id = None
        self._history.clear()

    def match(self, nav: NavigationState) -> MapMatchedPosition:
        if not self._in_coverage(nav.x, nav.y):
            return MapMatchedPosition(
                timestamp=nav.timestamp,
                lat_snapped=nav.lat,
                lon_snapped=nav.lon,
                heading_snapped_deg=nav.heading_deg,
                road_segment_id=-1,
                confidence_score=0.0,
                is_on_road_network=False,
                status=MapStatus.MAP_DATA_NOT_AVAILABLE,
            )
        cands: list[tuple[RoadSegment, float, float, float, float]] = []
        for seg in self.segments:
            px, py, t, dist = seg.project(nav.x, nav.y)
            if dist <= MAX_SEARCH_RADIUS_M:
                cands.append((seg, px, py, t, dist))
        if not cands:
            return MapMatchedPosition(
                timestamp=nav.timestamp,
                lat_snapped=nav.lat,
                lon_snapped=nav.lon,
                heading_snapped_deg=nav.heading_deg,
                road_segment_id=-1,
                confidence_score=0.0,
                is_on_road_network=False,
                status=MapStatus.OFF_NETWORK,
            )

        best_score = -1e18
        best = cands[0]
        yaw = nav.yaw
        for seg, px, py, t, dist in cands:
            emit = math.exp(-0.5 * (dist / max(4.0, nav.pos_std_m)) ** 2)
            dh = abs(wrap_angle(seg.heading_rad() - yaw))
            dh = min(dh, math.pi - dh)
            head = math.exp(-0.5 * (dh / 0.6) ** 2)
            trans = 1.0
            if self._prev_id is not None:
                trans = 1.15 if seg.id == self._prev_id else 0.75
                # adjacent if endpoints close
                prev = next((s for s in self.segments if s.id == self._prev_id), None)
                if prev is not None:
                    ends = [
                        math.hypot(seg.ax - prev.ax, seg.ay - prev.ay),
                        math.hypot(seg.ax - prev.bx, seg.ay - prev.by),
                        math.hypot(seg.bx - prev.ax, seg.by - prev.ay),
                        math.hypot(seg.bx - prev.bx, seg.by - prev.by),
                    ]
                    if min(ends) < 8.0:
                        trans = 1.05
            score = emit * head * trans
            if score > best_score:
                best_score = score
                best = (seg, px, py, t, dist)

        seg, px, py, t, dist = best
        self._prev_id = seg.id
        conf = float(max(0.0, min(1.0, best_score)))
        on = dist < 25.0
        lat, lon = _ll_from_nav(nav, px, py)
        return MapMatchedPosition(
            timestamp=nav.timestamp,
            lat_snapped=lat,
            lon_snapped=lon,
            heading_snapped_deg=heading_from_east_ccw_rad(seg.heading_rad()),
            road_segment_id=seg.id,
            confidence_score=conf if on else conf * 0.4,
            is_on_road_network=on,
            status=MapStatus.ON_NETWORK if on else MapStatus.OFF_NETWORK,
        )


def _ll_from_nav(nav: NavigationState, px: float, py: float) -> tuple[float, float]:
    # Reconstruct using same scale as nav lat/lon vs x/y
    # dlat/dy ≈ (nav.lat difference). Use local meters.
    from .geo import LocalTangent

    # invert approximately from current nav
    # We don't have origin here; pipeline will overwrite lat/lon via origin.
    return nav.lat, nav.lon
