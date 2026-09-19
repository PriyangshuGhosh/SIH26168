from __future__ import annotations

from pathlib import Path

from sih26168_map_matching.map_matcher import MapMatcher
from sih26168_map_matching.types import NavigationState

OSM_PACK = (
    Path(__file__).resolve().parents[2]
    / "data/maps/regions/r_12p96830_77p59103_12p97503_77p59815.roadpack"
)


def test_real_osm_roadpack_offline_match():
    assert OSM_PACK.is_file()
    matcher = MapMatcher.from_path(OSM_PACK)
    s = NavigationState(0.0, 12.9716, 77.5946, yaw_rad=1.2)
    out = matcher.match(s)
    assert out.match_status != "NO_MAP_DATA"
    assert out.lat_snapped != 0.0 or out.lon_snapped != 0.0
    far = matcher.match(NavigationState(1.0, -33.86, 151.21))
    assert far.match_status == "OUTSIDE_MAP"
    assert far.match_valid is False
    assert abs(far.lat_snapped + 33.86) < 1e-12


def test_member5_output_fields_present():
    matcher = MapMatcher.from_path(OSM_PACK)
    out = matcher.match(NavigationState(0.0, 12.9716, 77.5946))
    for name in (
        "timestamp",
        "lat_snapped",
        "lon_snapped",
        "heading_snapped_rad",
        "road_segment_id",
        "confidence_score",
        "is_on_road_network",
        "map_available",
        "match_valid",
        "match_status",
    ):
        assert hasattr(out, name)
