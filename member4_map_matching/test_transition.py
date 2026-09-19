"""
Member 4 - Transition probability test.

Uses two nearby road nodes from the saved OSM graph.
"""

import math
import networkx as nx

from osm_downloader import load_graph
from candidate_generator import generate_candidates
from transition_model import (
    calculate_network_distance,
    calculate_transition_probability,
    haversine_distance_m,
)


GRAPH_PATH = "data/osm/test_2km.graphml"
CANDIDATE_RADIUS_M = 30.0


def main():

    print("=" * 70)
    print("MEMBER 4 - TRANSITION PROBABILITY TEST")
    print("=" * 70)

    print("\nLoading offline OSM road graph...")
    graph = load_graph(GRAPH_PATH)

    # Select one road node near the original test location.
    start_node = min(
        graph.nodes,
        key=lambda node: (
            (float(graph.nodes[node]["y"]) - 12.9720) ** 2
            + (float(graph.nodes[node]["x"]) - 77.5950) ** 2
        ),
    )

    # Select one directly connected neighboring node.
    neighbors = list(graph.successors(start_node))

    if not neighbors:
        neighbors = list(graph.predecessors(start_node))

    if not neighbors:
        print("\nNo neighboring road node found.")
        return

    next_node = neighbors[0]

    latitude_1 = float(graph.nodes[start_node]["y"])
    longitude_1 = float(graph.nodes[start_node]["x"])

    latitude_2 = float(graph.nodes[next_node]["y"])
    longitude_2 = float(graph.nodes[next_node]["x"])

    print("\nState 1 GPS position:")
    print(f"Latitude  : {latitude_1}")
    print(f"Longitude : {longitude_1}")

    print("\nState 2 GPS position:")
    print(f"Latitude  : {latitude_2}")
    print(f"Longitude : {longitude_2}")

    # ---------------------------------------------------------
    # GENERATE CANDIDATES
    # ---------------------------------------------------------
    candidates_1 = generate_candidates(
        graph=graph,
        latitude=latitude_1,
        longitude=longitude_1,
        radius_m=CANDIDATE_RADIUS_M,
    )

    candidates_2 = generate_candidates(
        graph=graph,
        latitude=latitude_2,
        longitude=longitude_2,
        radius_m=CANDIDATE_RADIUS_M,
    )

    print(f"\nState 1 candidates: {len(candidates_1)}")
    print(f"State 2 candidates: {len(candidates_2)}")

    if not candidates_1 or not candidates_2:
        print("\nNot enough candidates for transition test.")
        return

    # ---------------------------------------------------------
    # OBSERVED DISTANCE
    # ---------------------------------------------------------
    observed_distance = haversine_distance_m(
        latitude_1,
        longitude_1,
        latitude_2,
        longitude_2,
    )

    print(f"\nObserved movement: {observed_distance:.2f} m")

    # ---------------------------------------------------------
    # TRANSITION PROBABILITIES
    # ---------------------------------------------------------
    print("\nTransition probabilities:")

    for i, previous_candidate in enumerate(candidates_1, start=1):

        for j, current_candidate in enumerate(candidates_2, start=1):

            network_distance = calculate_network_distance(
                graph,
                previous_candidate,
                current_candidate,
            )

            probability = calculate_transition_probability(
                network_distance_m=network_distance,
                observed_distance_m=observed_distance,
            )

            print("\n----------------------------------------")
            print(f"Previous candidate: #{i}")
            print(f"Current candidate : #{j}")
            print(f"Network distance  : {network_distance:.2f} m")
            print(f"Observed distance : {observed_distance:.2f} m")
            print(
                f"Transition probability: "
                f"{probability:.10f}"
            )


if __name__ == "__main__":
    main()