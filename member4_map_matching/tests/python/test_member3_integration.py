"""Member 3 → Member 4 contract integration (Python adapter)."""

from __future__ import annotations

import math

from sih26168_map_matching.map_matcher import MapMatcher
from sih26168_map_matching.road_graph import build_synthetic_grid
from sih26168_map_matching.types import NavigationState


def test_member3_navigation_state_fields_consumed():
    """Ensure Member 4 consumes the Member 3 field set (not a parallel schema)."""
    matcher = MapMatcher(build_synthetic_grid())
    state = NavigationState(
        timestamp=10.0,
        latitude=12.9716,
        longitude=77.5946,
        altitude=920.0,
        v_x=8.0,
        v_y=0.1,
        yaw_rad=math.pi / 2,
        position_cov_m2=((9.0, 0.1), (0.1, 9.0)),
        mode="DEAD_RECKONING",
    )
    out = matcher.match(state)
    assert out.timestamp == 10.0
    assert hasattr(out, "lat_snapped")
    assert hasattr(out, "lon_snapped")
    assert hasattr(out, "heading_snapped_rad")
    assert hasattr(out, "road_segment_id")
    assert hasattr(out, "confidence_score")
    assert hasattr(out, "is_on_road_network")
    assert 0.0 <= out.confidence_score <= 1.0 + 1e-9
