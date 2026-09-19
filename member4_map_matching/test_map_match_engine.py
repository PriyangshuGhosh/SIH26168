"""
Member 4 - MapMatcher Engine Test

Tests the complete reusable MapMatcher API.
"""

from osm_downloader import load_graph
from navigation_state import NavigationState, NavigationMode
from map_match_engine import MapMatcher


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
    print("MEMBER 4 - MAPMATCHER ENGINE TEST")
    print("=" * 70)

    print("\n[1] Loading offline OSM road graph...")

    graph = load_graph(GRAPH_PATH)

    print("\n[2] Creating MapMatcher engine...")

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    print("MapMatcher created successfully.")

    print("\n[3] Running complete map-matching pipeline...")

    results = matcher.match(
        NAVIGATION_STATES
    )

    print(
        f"Map-matched positions: "
        f"{len(results)}"
    )

    print("\n[4] FINAL RESULTS")

    for index, result in enumerate(
        results,
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

    assert len(results) == len(
        NAVIGATION_STATES
    )

    assert all(
        result.is_on_road_network
        for result in results
    )

    assert all(
        0.0 <= result.confidence_score <= 1.0
        for result in results
    )

    print("\n" + "=" * 70)
    print("MAPMATCHER ENGINE TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()