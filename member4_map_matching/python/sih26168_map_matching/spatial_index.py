"""In-memory AABB spatial index (deterministic; mirrors SQLite R-tree queries)."""

from __future__ import annotations

from dataclasses import dataclass

from .road_graph import RoadNetwork, RoadSegment


@dataclass
class Aabb:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class SpatialIndex:
    """Simple R-tree-like AABB index. For small offline maps this is exact.

    Query semantics match SQLite R*Tree overlap: return segments whose
    bounding box intersects the query box.
    """

    def __init__(self, network: RoadNetwork):
        self._segments = list(network.segments.values())

    def query_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> list[RoadSegment]:
        hits: list[RoadSegment] = []
        for seg in self._segments:
            if (
                seg.min_lon <= max_lon
                and seg.max_lon >= min_lon
                and seg.min_lat <= max_lat
                and seg.max_lat >= min_lat
            ):
                hits.append(seg)
        return hits
