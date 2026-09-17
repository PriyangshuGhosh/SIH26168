"""Contracts aligned with Member 3 NavigationState and Member 5 MapMatchedPosition."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Sequence


@dataclass
class NavigationState:
    """Python mirror of sih26168::member3::NavigationState.

    Prefer this adapter over inventing a parallel navigation schema.
    position_sigma_m is derived from the diagonal of position_cov_m2 unless set.
    """

    timestamp: float
    latitude: float
    longitude: float
    altitude: float = 0.0
    v_x: float = 0.0
    v_y: float = 0.0
    yaw_rad: float = 0.0
    position_cov_m2: Sequence[Sequence[float]] = field(
        default_factory=lambda: ((0.5, 0.0), (0.0, 0.5))
    )
    mode: str = "DEAD_RECKONING"
    heading_valid: bool = True
    _position_sigma_m: float | None = None

    @property
    def position_sigma_m(self) -> float:
        if self._position_sigma_m is not None:
            return max(self._position_sigma_m, 1e-3)
        c00 = float(self.position_cov_m2[0][0])
        c11 = float(self.position_cov_m2[1][1])
        return max(sqrt(max(c00, c11, 0.0)), 1e-3)

    @position_sigma_m.setter
    def position_sigma_m(self, value: float) -> None:
        self._position_sigma_m = value


@dataclass
class RoadCandidate:
    road_segment_id: int
    road_segment_label: str
    projected_latitude: float
    projected_longitude: float
    distance_m: float
    road_heading_rad: float
    fraction_along: float = 0.0
    u_node: int = -1
    v_node: int = -1
    length_m: float = 0.0


@dataclass
class MapMatchedPosition:
    """Matches docs/WORK_DISTRIBUTION.md and member5 map_matching_types.h."""

    timestamp: float
    lat_snapped: float
    lon_snapped: float
    heading_snapped_rad: float
    road_segment_id: int
    confidence_score: float
    is_on_road_network: bool
    distance_to_road_m: float = 0.0
