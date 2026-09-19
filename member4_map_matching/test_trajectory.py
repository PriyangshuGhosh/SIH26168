"""
Member 4 - Trajectory Map Matching Test

Tests the HMM map matcher on a sequence of
NavigationState positions.
"""

from osm_downloader import load_graph
from navigation_state import (
    NavigationState,
    NavigationMode,
)
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
        latitude=12.9719000,
        longitude=77.5949000,
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
        timestamp=2.0,
        latitude=12.9717500,
        longitude=77.5955000,
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
        timestamp=3.0,
        latitude=12.9716000,
        longitude=77.5961000,
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
        timestamp=4.0,
        latitude=12.9714500,
        longitude=77.5967000,
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

    print("=" * 80)
    print("MEMBER 4 - TRAJECTORY MAP MATCHING TEST")
    print("=" * 80)

    print("\n[1] Loading offline OSM road graph...")

    graph = load_graph(GRAPH_PATH)

    print("\n[2] Creating MapMatcher...")

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    print("MapMatcher created successfully.")

    print("\n[3] Running trajectory map matching...")

    results = matcher.match(
        NAVIGATION_STATES
    )

    print(
        f"Input NavigationStates : "
        f"{len(NAVIGATION_STATES)}"
    )

    print(
        f"Output MapMatchedPositions : "
        f"{len(results)}"
    )

    print("\n[4] MATCHED TRAJECTORY")

    for index, result in enumerate(
        results,
        start=1,
    ):

        print("\n" + "-" * 70)

        print(
            f"State {index}"
        )

        print(
            f"Timestamp       : "
            f"{result.timestamp}"
        )

        print(
            f"GPS input       : "
            f"{NAVIGATION_STATES[index - 1].latitude}, "
            f"{NAVIGATION_STATES[index - 1].longitude}"
        )

        print(
            f"Snapped position: "
            f"{result.lat_snapped}, "
            f"{result.lon_snapped}"
        )

        print(
            f"Road segment    : "
            f"{result.road_segment_id}"
        )

        print(
            f"Heading (rad)   : "
            f"{result.heading_snapped_rad}"
        )

        print(
            f"Confidence      : "
            f"{result.confidence_score}"
        )

        print(
            f"On road         : "
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

    print("\n" + "=" * 80)
    print("TRAJECTORY MAP MATCHING TEST PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()