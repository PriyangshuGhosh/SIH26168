"""
Member 4 - Map Matching Benchmark

Measures:

1. Number of navigation states
2. Number of successful matches
3. Average GPS-to-road distance
4. Maximum GPS-to-road distance
5. Total processing time
6. Average processing time per state
"""

import time

from osm_downloader import load_graph
from navigation_state import (
    NavigationState,
    NavigationMode,
)
from map_match_engine import MapMatcher
from transition_model import haversine_distance_m


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
    print("MEMBER 4 - MAP MATCHING PERFORMANCE BENCHMARK")
    print("=" * 80)

    print("\n[1] Loading offline OSM road graph...")

    graph = load_graph(GRAPH_PATH)

    print("\n[2] Creating MapMatcher...")

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    print("\n[3] Running benchmark...")

    start_time = time.perf_counter()

    results = matcher.match(
        NAVIGATION_STATES
    )

    end_time = time.perf_counter()

    total_time = end_time - start_time

    print("\n[4] CALCULATING METRICS")

    distances = []

    for state, result in zip(
        NAVIGATION_STATES,
        results,
    ):

        distance = haversine_distance_m(
            state.latitude,
            state.longitude,
            result.lat_snapped,
            result.lon_snapped,
        )

        distances.append(distance)

    successful_matches = sum(
        result.is_on_road_network
        for result in results
    )

    average_distance = (
        sum(distances) / len(distances)
        if distances
        else 0.0
    )

    maximum_distance = (
        max(distances)
        if distances
        else 0.0
    )

    average_time = (
        total_time / len(NAVIGATION_STATES)
        if NAVIGATION_STATES
        else 0.0
    )

    print("\n" + "-" * 70)

    print(
        f"Navigation states       : "
        f"{len(NAVIGATION_STATES)}"
    )

    print(
        f"Successful matches      : "
        f"{successful_matches}"
    )

    print(
        f"Match success rate      : "
        f"{(successful_matches / len(NAVIGATION_STATES)) * 100:.2f}%"
    )

    print(
        f"Average GPS error       : "
        f"{average_distance:.4f} m"
    )

    print(
        f"Maximum GPS error       : "
        f"{maximum_distance:.4f} m"
    )

    print(
        f"Total processing time   : "
        f"{total_time:.6f} seconds"
    )

    print(
        f"Average time / state    : "
        f"{average_time:.6f} seconds"
    )

    print("-" * 70)

    print("\n[5] PER-STATE DISTANCES")

    for index, distance in enumerate(
        distances,
        start=1,
    ):

        print(
            f"State {index}: "
            f"{distance:.4f} m"
        )

    assert len(results) == len(
        NAVIGATION_STATES
    )

    assert successful_matches == len(
        NAVIGATION_STATES
    )

    print("\n" + "=" * 80)
    print("MAP MATCHING BENCHMARK COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()