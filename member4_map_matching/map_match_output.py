"""
Member 4 - Map Matching Output

Converts Viterbi candidates into the final
MapMatchedPosition interface.

Supports:

1. Dictionary-based GPS states
2. Member 3 NavigationState objects
"""

import math

from map_matched_position import MapMatchedPosition
from emission_model import get_candidate_heading
from navigation_state import NavigationState


def get_state_value(state, key):
    """Read a value from NavigationState or dictionary."""

    if isinstance(state, NavigationState):

        if key == "heading":
            return state.yaw

        return getattr(state, key)

    return state[key]


def calculate_confidence(
    state_scores,
    selected_index,
):
    """Calculate relative confidence for a selected candidate."""

    valid_scores = [
        score
        for score in state_scores
        if not math.isinf(score)
    ]

    if not valid_scores:
        return 0.0

    selected_score = state_scores[selected_index]

    if math.isinf(selected_score):
        return 0.0

    shifted_scores = [
        math.exp(score - selected_score)
        for score in valid_scores
    ]

    total = sum(shifted_scores)

    if total <= 0:
        return 0.0

    confidence = 1.0 / total

    return max(
        0.0,
        min(1.0, confidence),
    )


def create_map_matched_position(
    graph,
    candidate,
    gps_state,
    confidence_score,
) -> MapMatchedPosition:
    """Convert selected candidate into final output."""

    road_heading = get_candidate_heading(
        graph,
        candidate,
    )

    timestamp = get_state_value(
        gps_state,
        "timestamp",
    )

    return MapMatchedPosition(
        timestamp=timestamp,
        lat_snapped=candidate.snapped_latitude,
        lon_snapped=candidate.snapped_longitude,
        heading_snapped_rad=road_heading,
        road_segment_id=candidate.road_segment_id,
        confidence_score=confidence_score,
        is_on_road_network=True,
    )