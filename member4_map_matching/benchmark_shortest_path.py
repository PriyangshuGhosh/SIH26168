"""
Member 4 - Shortest Path Performance Benchmark

Measures the performance of NetworkX shortest-path
calculations used by the HMM transition model.
"""

import time

from osm_downloader import load_graph
from candidate_generator import generate_candidates
from transition_model import calculate_network_distance


GRAPH_PATH = "data/osm/test_2km.graphml"


GPS_STATES = [
    {
        "latitude": 12.9720538,
        "longitude": 77.594311,
    },
    {
        "latitude": 12.9719,
        "longitude": 77.5949,
    },
    {
        "latitude": 12.97175,
        "longitude": 77.5955,
    },
    {
        "latitude": 12.9716,
        "longitude": 77.5961,
    },
    {
        "latitude": 12.97145,
        "longitude": 77.5967,
    },
]


print("=" * 80)
print()
print("# MEMBER 4 - SHORTEST PATH PERFORMANCE BENCHMARK")
print()


# ---------------------------------------------------------
# 1. Load graph
# ---------------------------------------------------------

print("[1] Loading offline OSM graph...")

graph = load_graph(GRAPH_PATH)

print()


# ---------------------------------------------------------
# 2. Generate candidates
# ---------------------------------------------------------

print("[2] Generating candidates...")

all_candidates = []

for state in GPS_STATES:

    candidates = generate_candidates(
        graph=graph,
        latitude=state["latitude"],
        longitude=state["longitude"],
        radius_m=30.0,
    )

    all_candidates.append(candidates)


for index, candidates in enumerate(all_candidates, start=1):
    print(
        f"State {index} candidates : {len(candidates)}"
    )

print()


# ---------------------------------------------------------
# 3. Benchmark network-distance calculations
# ---------------------------------------------------------

print("[3] Benchmarking network-distance calculations...")

total_calculations = 0
successful_calculations = 0

start_time = time.perf_counter()


for state_index in range(
    len(all_candidates) - 1
):

    previous_candidates = all_candidates[state_index]
    current_candidates = all_candidates[state_index + 1]

    for previous_candidate in previous_candidates:

        for current_candidate in current_candidates:

            network_distance = calculate_network_distance(
                graph=graph,
                previous_candidate=previous_candidate,
                current_candidate=current_candidate,
            )

            total_calculations += 1

            if network_distance != float("inf"):
                successful_calculations += 1


end_time = time.perf_counter()


total_time = end_time - start_time


# ---------------------------------------------------------
# 4. Results
# ---------------------------------------------------------

print()
print("-" * 80)

print(
    f"Total network-distance calculations : "
    f"{total_calculations}"
)

print(
    f"Successful calculations             : "
    f"{successful_calculations}"
)

print(
    f"Total calculation time              : "
    f"{total_time:.6f} seconds"
)

if total_calculations > 0:

    average_time = (
        total_time
        / total_calculations
    )

    print(
        f"Average time / calculation          : "
        f"{average_time:.6f} seconds"
    )

print("-" * 80)

print()
print("SHORTEST PATH BENCHMARK COMPLETED")
print()
print("=" * 80)