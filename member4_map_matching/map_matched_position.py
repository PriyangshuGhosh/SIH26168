"""
Member 4 - Map Matched Position

Defines the final output interface of the
offline HMM map-matching engine.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class MapMatchedPosition:
    """
    Final map-matched navigation output.
    """

    timestamp: float

    lat_snapped: float

    lon_snapped: float

    heading_snapped_rad: float

    road_segment_id: Any

    confidence_score: float

    is_on_road_network: bool