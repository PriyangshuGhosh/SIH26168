"""
Member 4 - NavigationState Integration Test

Tests the Member 3 NavigationState interface
with the Member 4 HMM map-matching engine.
"""

from osm_downloader import load_graph
from navigation_state import NavigationState, NavigationMode
from viterbi import viterbi_map_match
from map_match_output import (
    create_map_matched_position,
    calculate_confidence,
)


GRAPH_PATH = "data/osm/test_2km.graphml"


NAVIGATION_STATES = [
    NavigationState(
        timestamp=0.0,
        latitude=12.9720538,
        longitude=77.594311,
        altitude=0.0,
        vx=15.0,
        vy=0.0,
        yaw=0.0,
        covariance=[
            [1.0, 0.0],
            [0.0, 1.0],
        ],
        mode=NavigationMode.DEAD_RECKONING,
    ),
    NavigationState(
        timestamp=1.0,
        latitude=12.9711672,
        longitude=77.5972449,
        altitude=0.0,
        vx=15.0,
        vy=0.0,
        yaw=0.0,
        covariance=[
            [1.0, 0.0],
            [0.0, 1.0],
        ],
        mode=NavigationMode.DEAD_RECKONING,
    ),
]


def main():

    print("=" * 70)
    print("MEMBER 4 - NAVIGATIONSTATE INTEGRATION TEST")
    print("=" * 70)

    print("\n[1] Loading offline OSM road graph...")

    graph = load_graph(GRAPH_PATH)

    print("\n[2] Running Viterbi with Member 3 NavigationState...")

    best_sequence, scores, all_candidates = viterbi_map_match(
        graph=graph,
        gps_states=NAVIGATION_STATES,
        candidate_radius_m=30.0,
    )

    print(
        f"Selected candidates: "
        f"{len(best_sequence)}"
    )

    print("\n[3] Creating MapMatchedPosition outputs...")

    final_positions = []

    for t, (candidate, navigation_state) in enumerate(
        zip(best_sequence, NAVIGATION_STATES)
    ):

        selected_index = all_candidates[t].index(candidate)

        confidence = calculate_confidence(
            state_scores=scores[t],
            selected_index=selected_index,
        )

        result = create_map_matched_position(
            graph=graph,
            candidate=candidate,
            gps_state=navigation_state,
            confidence_score=confidence,
        )

        final_positions.append(result)

    print(
        "\n[4] FINAL NavigationState → "
        "MapMatchedPosition RESULTS"
    )

    for index, result in enumerate(
        final_positions,
        start=1,
    ):

        print("\n" + "-" * 60)

        print(
            f"Navigation State       : {index}"
        )

        print(
            f"Timestamp              : "
            f"{result.timestamp}"
        )

        print(
            f"Snapped latitude       : "
            f"{result.lat_snapped}"
        )

        print(
            f"Snapped longitude      : "
            f"{result.lon_snapped}"
        )

        print(
            f"Snapped heading (rad)  : "
            f"{result.heading_snapped_rad}"
        )

        print(
            f"Road segment ID        : "
            f"{result.road_segment_id}"
        )

        print(
            f"Confidence score       : "
            f"{result.confidence_score}"
        )

        print(
            f"On road network        : "
            f"{result.is_on_road_network}"
        )

    print("\n" + "=" * 70)

    print(
        "NavigationState INTEGRATION TEST PASSED"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()