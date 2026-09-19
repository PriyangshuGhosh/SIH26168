"""
Member 4 - Candidate generation test.

Tests whether road segments can be found within
a 30 meter radius of a drifting GPS position.
"""

from osm_downloader import load_graph
from candidate_generator import generate_candidates


GRAPH_PATH = "data/osm/test_2km.graphml"

GPS_LATITUDE = 12.9720
GPS_LONGITUDE = 77.5950

CANDIDATE_RADIUS_M = 30.0


def main():

    print("=" * 70)
    print("MEMBER 4 - 30M ROAD CANDIDATE GENERATION TEST")
    print("=" * 70)

    print("\nLoading offline OSM road graph...")

    graph = load_graph(
        GRAPH_PATH
    )

    print("\nInput GPS position:")
    print(
        f"Latitude  : {GPS_LATITUDE}"
    )
    print(
        f"Longitude : {GPS_LONGITUDE}"
    )

    print(
        f"\nCandidate radius: "
        f"{CANDIDATE_RADIUS_M} meters"
    )

    candidates = generate_candidates(
        graph=graph,
        latitude=GPS_LATITUDE,
        longitude=GPS_LONGITUDE,
        radius_m=CANDIDATE_RADIUS_M,
    )

    print(
        f"\nCandidates found: "
        f"{len(candidates)}"
    )

    print("\nCandidate roads:")

    for i, candidate in enumerate(
        candidates[:10],
        start=1,
    ):

        print("\n----------------------------------------")

        print(
            f"Candidate #{i}"
        )

        print(
            f"Road segment ID : "
            f"{candidate.road_segment_id}"
        )

        print(
            f"Distance        : "
            f"{candidate.distance_m:.2f} m"
        )

        print(
            f"Snapped latitude : "
            f"{candidate.snapped_latitude}"
        )

        print(
            f"Snapped longitude: "
            f"{candidate.snapped_longitude}"
        )

        print(
            f"Highway type    : "
            f"{candidate.highway}"
        )


if __name__ == "__main__":
    main()