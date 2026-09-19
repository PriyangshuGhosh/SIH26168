"""
Member 4 - 20 Point Accuracy Benchmark

Tests the map matcher using a longer connected road trajectory.

Noise levels:
5 m
10 m
15 m
20 m
25 m
"""

import math
import random

import osmnx as ox

from navigation_state import (
    NavigationState,
    NavigationMode,
)

from map_match_engine import MapMatcher


GRAPH_PATH = "data/osm/test_2km.graphml"

NOISE_LEVELS_M = [5, 10, 15, 20, 25]

NUM_STATES = 20

RANDOM_SEED = 42


def haversine_distance_m(
    lat1,
    lon1,
    lat2,
    lon2,
):
    earth_radius = 6371000.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    return (
        2
        * earth_radius
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a),
        )
    )


def create_connected_trajectory(
    graph,
    num_states,
):
    """
    Create a connected trajectory by walking through
    neighboring OSM road nodes.
    """

    print("[1] Creating 20-point connected trajectory...")

    start_node = max(
        graph.nodes,
        key=lambda node: graph.degree(node),
    )

    trajectory = [start_node]
    current_node = start_node
    previous_node = None

    for _ in range(num_states - 1):

        neighbors = list(
            graph.successors(current_node)
        )

        # Avoid immediately going backwards.
        filtered = [
            node
            for node in neighbors
            if node != previous_node
        ]

        if not filtered:
            filtered = neighbors

        if not filtered:
            break

        # Deterministic selection.
        next_node = filtered[0]

        previous_node = current_node
        current_node = next_node

        trajectory.append(current_node)

    if len(trajectory) < num_states:
        raise RuntimeError(
            "Could not create a 20-point connected trajectory."
        )

    return trajectory


def add_noise(
    latitude,
    longitude,
    max_noise_m,
):
    """
    Add random GNSS noise up to max_noise_m.
    """

    angle = random.uniform(
        0,
        2 * math.pi,
    )

    distance = random.uniform(
        0,
        max_noise_m,
    )

    meters_per_degree_lat = 111320.0

    meters_per_degree_lon = (
        111320.0
        * math.cos(
            math.radians(latitude)
        )
    )

    delta_lat = (
        distance
        * math.cos(angle)
        / meters_per_degree_lat
    )

    delta_lon = (
        distance
        * math.sin(angle)
        / meters_per_degree_lon
    )

    return (
        latitude + delta_lat,
        longitude + delta_lon,
        distance,
    )


def create_navigation_states(
    true_positions,
    noise_level,
):
    states = []

    for index, (
        latitude,
        longitude,
    ) in enumerate(true_positions):

        noisy_latitude, noisy_longitude, _ = (
            add_noise(
                latitude,
                longitude,
                noise_level,
            )
        )

        states.append(
            NavigationState(
                timestamp=float(index),
                latitude=noisy_latitude,
                longitude=noisy_longitude,
                altitude=0.0,
                vx=10.0,
                vy=0.0,
                yaw=0.0,
                covariance=[],
                mode=NavigationMode.DEAD_RECKONING,
            )
        )

    return states


def run_test(
    graph,
    true_positions,
    noise_level,
):
    states = create_navigation_states(
        true_positions,
        noise_level,
    )

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    try:
        results = matcher.match(states)
    except ValueError:
        return None

    original_errors = []
    matched_errors = []

    for index, result in enumerate(results):

        true_lat, true_lon = (
            true_positions[index]
        )

        noisy_lat = states[index].latitude
        noisy_lon = states[index].longitude

        original_error = haversine_distance_m(
            true_lat,
            true_lon,
            noisy_lat,
            noisy_lon,
        )

        matched_error = haversine_distance_m(
            true_lat,
            true_lon,
            result.lat_snapped,
            result.lon_snapped,
        )

        original_errors.append(
            original_error
        )

        matched_errors.append(
            matched_error
        )

    avg_original = (
        sum(original_errors)
        / len(original_errors)
    )

    avg_matched = (
        sum(matched_errors)
        / len(matched_errors)
    )

    improvement = (
        avg_original
        - avg_matched
    )

    improvement_percentage = (
        improvement
        / avg_original
        * 100
        if avg_original > 0
        else 0
    )

    return (
        avg_original,
        avg_matched,
        improvement,
        improvement_percentage,
        len(results),
    )


if __name__ == "__main__":

    random.seed(RANDOM_SEED)

    print("=" * 95)
    print()
    print(
        "MEMBER 4 - 20 POINT MAP MATCHING "
        "ACCURACY BENCHMARK"
    )
    print()
    print("=" * 95)

    print("\n[1] Loading offline OSM graph...")

    graph = ox.load_graphml(
        GRAPH_PATH
    )

    print(
        f"Nodes : {len(graph.nodes)}"
    )

    print(
        f"Edges : {len(graph.edges)}"
    )

    trajectory_nodes = (
        create_connected_trajectory(
            graph,
            NUM_STATES,
        )
    )

    true_positions = []

    print("\n[2] True trajectory:")

    for index, node in enumerate(
        trajectory_nodes
    ):

        node_data = graph.nodes[node]

        latitude = float(
            node_data["y"]
        )

        longitude = float(
            node_data["x"]
        )

        true_positions.append(
            (
                latitude,
                longitude,
            )
        )

        print(
            f"Point {index + 1:02d}: "
            f"{latitude:.7f}, "
            f"{longitude:.7f}"
        )

    print("\n")
    print("=" * 95)

    print(
        f"{'Noise':>8} | "
        f"{'Original Error':>16} | "
        f"{'Matched Error':>16} | "
        f"{'Improvement':>14} | "
        f"{'Improvement %':>14} | "
        f"{'Matches':>8}"
    )

    print("-" * 95)

    for noise_level in NOISE_LEVELS_M:

        result = run_test(
            graph,
            true_positions,
            noise_level,
        )

        if result is None:

            print(
                f"{noise_level:>7} m | "
                f"MAP MATCHING FAILED"
            )

            continue

        (
            original,
            matched,
            improvement,
            percentage,
            matches,
        ) = result

        print(
            f"{noise_level:>7} m | "
            f"{original:>15.2f} m | "
            f"{matched:>15.2f} m | "
            f"{improvement:>13.2f} m | "
            f"{percentage:>13.2f}% | "
            f"{matches:>8}"
        )

    print("-" * 95)

    print()
    print(
        "20-POINT ACCURACY BENCHMARK COMPLETED"
    )