"""Uncertainty-aware road candidate generation."""

from __future__ import annotations

from .geometry import meters_to_deg_bbox, project_point_to_road
from .road_graph import RoadNetwork
from .spatial_index import SpatialIndex
from .types import NavigationState, RoadCandidate


def search_radius_m(
    state: NavigationState,
    base_radius_m: float = 30.0,
    sigma_scale: float = 3.0,
    max_radius_m: float = 120.0,
) -> float:
    """Widen search with position uncertainty; never magically shrink uncertainty."""
    return min(max_radius_m, max(base_radius_m, sigma_scale * state.position_sigma_m))


def generate_candidates(
    state: NavigationState,
    network: RoadNetwork,
    index: SpatialIndex,
    base_radius_m: float = 30.0,
    max_candidates: int = 12,
) -> list[RoadCandidate]:
    radius = search_radius_m(state, base_radius_m=base_radius_m)
    min_lon, min_lat, max_lon, max_lat = meters_to_deg_bbox(
        state.latitude, state.longitude, radius
    )
    nearby = index.query_bbox(min_lon, min_lat, max_lon, max_lat)
    candidates: list[RoadCandidate] = []
    for seg in nearby:
        projection = project_point_to_road(
            state.latitude, state.longitude, seg.geometry
        )
        if projection.distance_m > radius:
            continue
        candidates.append(
            RoadCandidate(
                road_segment_id=seg.segment_id,
                road_segment_label=seg.label,
                projected_latitude=projection.projected_latitude,
                projected_longitude=projection.projected_longitude,
                distance_m=projection.distance_m,
                road_heading_rad=seg.heading_rad,
                fraction_along=projection.fraction_along,
                u_node=seg.u_node,
                v_node=seg.v_node,
                length_m=seg.length_m,
            )
        )
    candidates.sort(key=lambda c: c.distance_m)
    return candidates[:max_candidates]
