"""
Member 4 - Final End-to-End Test

Tests:

1. Offline OSM graph
2. Candidate generation
3. Emission model
4. Transition model
5. Viterbi HMM
6. Final MapMatchedPosition interface
"""

from osm_downloader import load_graph
from viterbi import viterbi_map_match
from map_match_output import (
    create_map_matched_position,
    calculate_confidence,
)


GRAPH_PATH = "data/osm/test_2km.graphml"


GPS_STATES = [
    {
        "timestamp": 0.0,
        "latitude": 12.9720538,
        "longitude": 77.594311,
        "heading": 0.0,
    },
    {
        "timestamp": 1.0,
        "latitude": 12.9711672,
        "longitude": 77.5972449,
        "heading": 0.0,
    },
]


def main():

    print("=" * 70)
    print("MEMBER 4 - FINAL END-TO-END MAP MATCHING TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # STEP 1 - LOAD OFFLINE OSM GRAPH
    # ---------------------------------------------------------

    print("\n[1] Loading offline OSM road graph...")

    graph = load_graph(
        GRAPH_PATH
    )

    # ---------------------------------------------------------
    # STEP 2 - RUN VITERBI
    # ---------------------------------------------------------

    print("\n[2] Running HMM Viterbi map matching...")

    best_sequence, scores, all_candidates = viterbi_map_match(
        graph=graph,
        gps_states=GPS_STATES,
        candidate_radius_m=30.0,
    )

    print(
        f"Selected candidates: "
        f"{len(best_sequence)}"
    )

    # ---------------------------------------------------------
    # STEP 3 - CONVERT TO FINAL INTERFACE
    # ---------------------------------------------------------

    print(
        "\n[3] Creating MapMatchedPosition outputs..."
    )

    final_positions = []

    for t, (candidate, gps_state) in enumerate(
        zip(best_sequence, GPS_STATES)
    ):

        selected_index = all_candidates[t].index(
            candidate
        )

        confidence = calculate_confidence(
            state_scores=scores[t],
            selected_index=selected_index,
        )

        result = create_map_matched_position(
            graph=graph,
            candidate=candidate,
            gps_state=gps_state,
            confidence_score=confidence,
        )

        final_positions.append(result)

    # ---------------------------------------------------------
    # STEP 4 - DISPLAY RESULTS
    # ---------------------------------------------------------

    print("\n[4] FINAL MAP-MATCHED RESULTS")

    for index, result in enumerate(
        final_positions,
        start=1,
    ):

        print("\n" + "-" * 60)

        print(
            f"GPS State              : {index}"
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

    # ---------------------------------------------------------
    # STEP 5 - SUCCESS
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("MEMBER 4 END-TO-END TEST COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()