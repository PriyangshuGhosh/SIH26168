"""
Member 4 - Noisy GNSS Trajectory Test

Tests whether the HMM map matcher can correct
small GNSS/dead-reckoning position errors by
snapping them to valid road geometry.
"""

from osm_downloader import load_graph
from map_match_engine import MapMatcher
from navigation_state import NavigationState, NavigationMode


GRAPH_PATH = "data/osm/test_2km.graphml"


def main():
    # ---------------------------------------------------------
    # 1. Load offline graph
    # ---------------------------------------------------------

    print("=" * 80)
    print()
    print("# MEMBER 4 - NOISY GNSS TRAJECTORY TEST")
    print()

    print("[1] Loading offline OSM graph...")

    graph = load_graph(GRAPH_PATH)

    print()

    # ---------------------------------------------------------
    # 2. Create noisy GNSS states
    # ---------------------------------------------------------

    print("[2] Creating noisy GNSS trajectory...")

    states = [
        NavigationState(
            timestamp=0.0,
            latitude=12.9720538,
            longitude=77.594311,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[
                [5.0, 0.0],
                [0.0, 5.0],
            ],
            mode=NavigationMode.DEAD_RECKONING,
        ),

        NavigationState(
            timestamp=1.0,
            latitude=12.97192,
            longitude=77.59498,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[
                [8.0, 0.0],
                [0.0, 8.0],
            ],
            mode=NavigationMode.DEAD_RECKONING,
        ),

        NavigationState(
            timestamp=2.0,
            latitude=12.97180,
            longitude=77.59560,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[
                [10.0, 0.0],
                [0.0, 10.0],
            ],
            mode=NavigationMode.DEAD_RECKONING,
        ),

        NavigationState(
            timestamp=3.0,
            latitude=12.97170,
            longitude=77.59590,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[
                [12.0, 0.0],
                [0.0, 12.0],
            ],
            mode=NavigationMode.DEAD_RECKONING,
        ),

        NavigationState(
            timestamp=4.0,
            latitude=12.97165,
            longitude=77.59600,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[
                [15.0, 0.0],
                [0.0, 15.0],
            ],
            mode=NavigationMode.DEAD_RECKONING,
        ),
    ]

    print(f"Navigation states : {len(states)}")
    print()

    # ---------------------------------------------------------
    # 3. Run map matcher
    # ---------------------------------------------------------

    print("[3] Running HMM map matcher...")

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    results = matcher.match(states)

    print()

    # ---------------------------------------------------------
    # 4. Display results
    # ---------------------------------------------------------

    print("[4] Map-matching results")
    print()
    print("-" * 80)

    for index, (state, result) in enumerate(
        zip(states, results),
        start=1,
    ):
        print(f"State {index}")

        print(
            f"Original GPS   : "
            f"{state.latitude:.7f}, "
            f"{state.longitude:.7f}"
        )

        print(
            f"Snapped GPS    : "
            f"{result.lat_snapped:.7f}, "
            f"{result.lon_snapped:.7f}"
        )

        print(
            f"Road segment   : "
            f"{result.road_segment_id}"
        )

        print(
            f"Confidence     : "
            f"{result.confidence_score:.6f}"
        )

        print(
            f"On road network: "
            f"{result.is_on_road_network}"
        )

        print("-" * 80)

    # ---------------------------------------------------------
    # 5. Final validation
    # ---------------------------------------------------------

    all_on_road = all(
        result.is_on_road_network
        for result in results
    )

    print()

    if all_on_road:
        print("NOISY GNSS MAP MATCHING TEST PASSED")
    else:
        print("NOISY GNSS MAP MATCHING TEST FAILED")

    print()
    print("=" * 80)


if __name__ == "__main__":
    main()