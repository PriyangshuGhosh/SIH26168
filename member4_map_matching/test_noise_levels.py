"""
Member 4 - Multi-Noise Accuracy Benchmark

Tests the HMM map matcher under different GNSS noise levels.

Noise levels:
5 m
10 m
15 m
20 m
25 m

The benchmark compares:

1. Original noisy GPS error
2. Map-matched error
3. Error improvement
4. Improvement percentage
"""

import math
import random

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point

from navigation_state import NavigationState, NavigationMode
from map_match_engine import MapMatcher


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

GRAPH_PATH = "data/osm/test_2km.graphml"

NOISE_LEVELS_M = [5, 10, 15, 20, 25]

NUM_STATES = 5

RANDOM_SEED = 42


# ---------------------------------------------------------
# Distance helper
# ---------------------------------------------------------

def haversine_distance_m(
    lat1,
    lon1,
    lat2,
    lon2,
):
    earth_radius_m = 6371000.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_m * c


# ---------------------------------------------------------
# Convert projected point to latitude/longitude
# ---------------------------------------------------------

def point_to_latlon(point, projected_crs):

    point_gdf = gpd.GeoDataFrame(
        geometry=[point],
        crs=projected_crs,
    )

    point_wgs84 = point_gdf.to_crs(
        "EPSG:4326"
    )

    geometry = point_wgs84.geometry.iloc[0]

    return geometry.y, geometry.x


# ---------------------------------------------------------
# Generate connected trajectory
# ---------------------------------------------------------

def create_true_trajectory(graph, num_states):

    print("[1] Creating connected road trajectory...")

    nodes = list(graph.nodes)

    # Pick a node with many nearby connections.
    start_node = max(
        nodes,
        key=lambda node: graph.degree(node),
    )

    current_node = start_node

    trajectory_nodes = [current_node]

    # Walk through connected roads.
    for _ in range(num_states - 1):

        neighbors = list(
            graph.successors(current_node)
        )

        if not neighbors:
            break

        # Choose the first available connected neighbor.
        next_node = neighbors[0]

        trajectory_nodes.append(next_node)

        current_node = next_node

    if len(trajectory_nodes) < num_states:
        raise RuntimeError(
            "Could not create a connected trajectory."
        )

    return trajectory_nodes[:num_states]


# ---------------------------------------------------------
# Create true road positions
# ---------------------------------------------------------

def create_true_positions(
    graph,
    trajectory_nodes,
):

    print("[2] Creating true road positions...")

    projected_graph = ox.project_graph(graph)

    true_positions = []

    for node in trajectory_nodes:

        node_data = graph.nodes[node]

        latitude = node_data["y"]
        longitude = node_data["x"]

        true_positions.append(
            (
                latitude,
                longitude,
            )
        )

    return true_positions


# ---------------------------------------------------------
# Add random GNSS noise
# ---------------------------------------------------------

def add_noise(
    latitude,
    longitude,
    noise_radius_m,
):

    # Random direction.
    angle = random.uniform(
        0,
        2 * math.pi,
    )

    # Random distance between 0 and requested noise.
    distance = random.uniform(
        0,
        noise_radius_m,
    )

    # Approximate conversion.
    meters_per_degree_lat = 111320.0

    meters_per_degree_lon = (
        111320.0
        * math.cos(math.radians(latitude))
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

    noisy_latitude = latitude + delta_lat
    noisy_longitude = longitude + delta_lon

    return (
        noisy_latitude,
        noisy_longitude,
        distance,
    )


# ---------------------------------------------------------
# Build NavigationStates
# ---------------------------------------------------------

def create_navigation_states(
    true_positions,
    noise_radius_m,
):

    states = []

    for index, (
        latitude,
        longitude,
    ) in enumerate(true_positions):

        noisy_latitude, noisy_longitude, _ = add_noise(
            latitude,
            longitude,
            noise_radius_m,
        )

        state = NavigationState(
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

        states.append(state)

    return states


# ---------------------------------------------------------
# Run one noise level
# ---------------------------------------------------------

def run_noise_test(
    graph,
    true_positions,
    noise_radius_m,
):

    states = create_navigation_states(
        true_positions,
        noise_radius_m,
    )

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    results = matcher.match(states)

    original_errors = []
    matched_errors = []

    for index, result in enumerate(results):

        true_latitude, true_longitude = (
            true_positions[index]
        )

        noisy_latitude = states[index].latitude
        noisy_longitude = states[index].longitude

        original_error = haversine_distance_m(
            true_latitude,
            true_longitude,
            noisy_latitude,
            noisy_longitude,
        )

        matched_error = haversine_distance_m(
            true_latitude,
            true_longitude,
            result.lat_snapped,
            result.lon_snapped,
        )

        original_errors.append(
            original_error
        )

        matched_errors.append(
            matched_error
        )

    average_original_error = (
        sum(original_errors)
        / len(original_errors)
    )

    average_matched_error = (
        sum(matched_errors)
        / len(matched_errors)
    )

    improvement = (
        average_original_error
        - average_matched_error
    )

    if average_original_error > 0:

        improvement_percentage = (
            improvement
            / average_original_error
            * 100
        )

    else:
        improvement_percentage = 0.0

    return (
        average_original_error,
        average_matched_error,
        improvement,
        improvement_percentage,
        len(results),
    )


# ---------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------

if __name__ == "__main__":

    random.seed(RANDOM_SEED)

    print("=" * 90)
    print()
    print("MEMBER 4 - MULTI-NOISE MAP MATCHING ACCURACY BENCHMARK")
    print()
    print("=" * 90)

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

    trajectory_nodes = create_true_trajectory(
        graph,
        NUM_STATES,
    )

    true_positions = create_true_positions(
        graph,
        trajectory_nodes,
    )

    print("\nTrue trajectory:")

    for index, (
        latitude,
        longitude,
    ) in enumerate(true_positions):

        print(
            f"Point {index + 1}: "
            f"{latitude:.7f}, "
            f"{longitude:.7f}"
        )

    print("\n")
    print("=" * 90)

    print(
        f"{'Noise':>8} | "
        f"{'Original Error':>16} | "
        f"{'Matched Error':>16} | "
        f"{'Improvement':>14} | "
        f"{'Improvement %':>14} | "
        f"{'Matches':>8}"
    )

    print("-" * 90)

    results = []

    for noise_level in NOISE_LEVELS_M:

        (
            original_error,
            matched_error,
            improvement,
            improvement_percentage,
            matches,
        ) = run_noise_test(
            graph,
            true_positions,
            noise_level,
        )

        results.append(
            (
                noise_level,
                original_error,
                matched_error,
                improvement,
                improvement_percentage,
                matches,
            )
        )

        print(
            f"{noise_level:>7.0f} m | "
            f"{original_error:>15.2f} m | "
            f"{matched_error:>15.2f} m | "
            f"{improvement:>13.2f} m | "
            f"{improvement_percentage:>13.2f}% | "
            f"{matches:>8}"
        )

    print("-" * 90)

    print("\nFINAL BENCHMARK SUMMARY")

    successful_levels = sum(
        1
        for result in results
        if result[5] == NUM_STATES
    )

    print(
        f"Noise levels tested     : "
        f"{len(NOISE_LEVELS_M)}"
    )

    print(
        f"Fully successful levels : "
        f"{successful_levels}/{len(NOISE_LEVELS_M)}"
    )

    print(
        "\nMULTI-NOISE BENCHMARK COMPLETED"
    )