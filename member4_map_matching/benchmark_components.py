"""
Member 4 - Component Performance Benchmark

Measures the time spent in:
1. Candidate generation
2. Viterbi map matching
"""

import time

from osm_downloader import load_graph
from navigation_state import (
    NavigationState,
    NavigationMode,
)
from candidate_generator import generate_candidates
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
        covariance=[[1.0, 0.0], [0.0, 1.0]],
        mode=NavigationMode.DEAD_RECKONING,
    ),
    NavigationState(
        timestamp=1.0,
        latitude=12.9719,
        longitude=77.5949,
        altitude=0.0,
        vx=15.0,
        vy=0.0,
        yaw=0.0,
        covariance=[[1.0, 0.0], [0.0, 1.0]],
        mode=NavigationMode.DEAD_RECKONING,
    ),
    NavigationState(
        timestamp=2.0,
        latitude=12.97175,
        longitude=77.5955,
        altitude=0.0,
        vx=15.0,
        vy=0.0,
        yaw=0.0,
        covariance=[[1.0, 0.0], [0.0, 1.0]],
        mode=NavigationMode.DEAD_RECKONING,
    ),
    NavigationState(
        timestamp=3.0,
        latitude=12.9716,
        longitude=77.5961,
        altitude=0.0,
        vx=15.0,
        vy=0.0,
        yaw=0.0,
        covariance=[[1.0, 0.0], [0.0, 1.0]],
        mode=NavigationMode.DEAD_RECKONING,
    ),
    NavigationState(
        timestamp=4.0,
        latitude=12.97145,
        longitude=77.5967,
        altitude=0.0,
        vx=15.0,
        vy=0.0,
        yaw=0.0,
        covariance=[[1.0, 0.0], [0.0, 1.0]],
        mode=NavigationMode.DEAD_RECKONING,
    ),
]


def main():

    print("=" * 80)
    print("MEMBER 4 - COMPONENT PERFORMANCE BENCHMARK")
    print("=" * 80)

    print("\n[1] Loading offline OSM graph...")

    graph = load_graph(GRAPH_PATH)

    # ---------------------------------------------------------
    # Candidate generation benchmark
    # ---------------------------------------------------------

    print("\n[2] Benchmarking candidate generation...")

    start = time.perf_counter()

    candidate_counts = []

    for state in NAVIGATION_STATES:

        candidates = generate_candidates(
            graph=graph,
            latitude=state.latitude,
            longitude=state.longitude,
            radius_m=30.0,
        )

        candidate_counts.append(
            len(candidates)
        )

    end = time.perf_counter()

    candidate_time = end - start

    print(
        f"Total candidate generation time : "
        f"{candidate_time:.6f} seconds"
    )

    print(
        f"Average candidate generation     : "
        f"{candidate_time / len(NAVIGATION_STATES):.6f} seconds/state"
    )

    print(
        f"Candidates per state             : "
        f"{candidate_counts}"
    )

    # ---------------------------------------------------------
    # Complete matcher benchmark
    # ---------------------------------------------------------

    print("\n[3] Benchmarking complete MapMatcher...")

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    start = time.perf_counter()

    results = matcher.match(
        NAVIGATION_STATES
    )

    end = time.perf_counter()

    matcher_time = end - start

    print(
        f"Total MapMatcher time            : "
        f"{matcher_time:.6f} seconds"
    )

    print(
        f"Average MapMatcher time           : "
        f"{matcher_time / len(NAVIGATION_STATES):.6f} seconds/state"
    )

    print(
        f"Results produced                 : "
        f"{len(results)}"
    )

    assert len(results) == len(
        NAVIGATION_STATES
    )

    print("\n" + "=" * 80)
    print("COMPONENT PERFORMANCE BENCHMARK COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()