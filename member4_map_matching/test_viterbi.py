"""
Member 4 - Viterbi HMM test.
"""

from osm_downloader import load_graph
from viterbi import viterbi_map_match


GRAPH_PATH = "data/osm/test_2km.graphml"


GPS_STATES = [
    {
        "latitude": 12.9720538,
        "longitude": 77.594311,
        "heading": 0.0,
    },
    {
        "latitude": 12.9711672,
        "longitude": 77.5972449,
        "heading": 0.0,
    },
]


def main():

    print("=" * 70)
    print("MEMBER 4 - VITERBI HMM MAP MATCHING TEST")
    print("=" * 70)

    print("\nLoading offline OSM road graph...")

    graph = load_graph(GRAPH_PATH)

    print("\nRunning Viterbi map matching...")

    best_sequence, scores, all_candidates = viterbi_map_match(
        graph=graph,
        gps_states=GPS_STATES,
        candidate_radius_m=30.0,
    )

    print("\nBest road sequence:")

    for i, candidate in enumerate(
        best_sequence,
        start=1,
    ):

        print("\n----------------------------------------")
        print(f"GPS State: {i}")
        print(
            f"Road segment ID: "
            f"{candidate.road_segment_id}"
        )
        print(
            f"Snapped latitude: "
            f"{candidate.snapped_latitude}"
        )
        print(
            f"Snapped longitude: "
            f"{candidate.snapped_longitude}"
        )
        print(
            f"Distance from GPS: "
            f"{candidate.distance_m:.2f} m"
        )


if __name__ == "__main__":
    main()