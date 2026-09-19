"""
Member 4 - Realistic Connected Trajectory Test

Purpose:
1. Select a connected road path from the offline OSM graph.
2. Create positions along that path.
3. Add controlled GNSS noise.
4. Run the HMM map matcher.
5. Compare noisy GPS with the true road position.
6. Measure map-matching error.
"""

import math
import random

import osmnx as ox

from osm_downloader import load_graph
from map_match_engine import MapMatcher


GRAPH_PATH = "data/osm/test_2km.graphml"

NUM_POINTS = 5
NOISE_METERS = [5.0, 8.0, 10.0, 12.0, 15.0]
RANDOM_SEED = 42


def haversine_distance_m(lat1, lon1, lat2, lon2):
    """Calculate distance between two latitude/longitude points."""

    earth_radius = 6371000.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * earth_radius * math.asin(math.sqrt(a))


def add_noise(lat, lon, noise_m, rng):
    """
    Add approximately noise_m meters of random GNSS noise.
    """

    angle = rng.uniform(0, 2 * math.pi)

    north_m = noise_m * math.cos(angle)
    east_m = noise_m * math.sin(angle)

    meters_per_degree_lat = 111320.0
    meters_per_degree_lon = (
        111320.0 * math.cos(math.radians(lat))
    )

    noisy_lat = lat + north_m / meters_per_degree_lat
    noisy_lon = lon + east_m / meters_per_degree_lon

    return noisy_lat, noisy_lon


def select_connected_path(graph, num_points):
    """
    Find a connected sequence of nodes in the road graph.
    """

    print("[2] Finding a connected road path...")

    # Pick a reasonably well-connected node.
    nodes = list(graph.nodes)

    for start_node in nodes:
        try:
            reachable = nx.single_source_shortest_path_length(
                graph,
                start_node,
                cutoff=20,
            )

            if len(reachable) >= num_points + 5:
                path_nodes = list(reachable.keys())[:num_points]

                if len(path_nodes) >= num_points:
                    print(
                        f"Connected path found with {len(path_nodes)} nodes."
                    )
                    return path_nodes

        except Exception:
            continue

    raise RuntimeError(
        "Could not find a connected road path."
    )


def main():

    print("=" * 80)
    print("MEMBER 4 - REALISTIC CONNECTED TRAJECTORY TEST")
    print("=" * 80)

    random.seed(RANDOM_SEED)
    rng = random.Random(RANDOM_SEED)

    # ---------------------------------------------------------
    # 1. Load graph
    # ---------------------------------------------------------

    print("\n[1] Loading offline OSM graph...")

    graph = load_graph(GRAPH_PATH)

    print(f"Nodes : {len(graph.nodes)}")
    print(f"Edges : {len(graph.edges)}")

    # ---------------------------------------------------------
    # 2. Select connected path
    # ---------------------------------------------------------

    print("\n[2] Selecting connected road trajectory...")

    # Use NetworkX directly.
    import networkx as nx

    # Find a node with a reasonably large connected neighborhood.
    start_node = max(
        graph.nodes,
        key=lambda node: graph.degree(node),
    )

    lengths = nx.single_source_shortest_path_length(
        graph,
        start_node,
        cutoff=30,
    )

    candidate_nodes = list(lengths.keys())

    if len(candidate_nodes) < NUM_POINTS:
        raise RuntimeError(
            "Not enough connected nodes found."
        )

    # Select nodes at increasing graph distance.
    selected_nodes = []

    for node in candidate_nodes:
        if node not in selected_nodes:
            selected_nodes.append(node)

        if len(selected_nodes) == NUM_POINTS:
            break

    print(
        f"Connected trajectory nodes selected : "
        f"{len(selected_nodes)}"
    )

    # ---------------------------------------------------------
    # 3. Convert nodes to road positions
    # ---------------------------------------------------------

    print("\n[3] Creating true road positions...")

    true_positions = []

    for node in selected_nodes:

        latitude = float(graph.nodes[node]["y"])
        longitude = float(graph.nodes[node]["x"])

        true_positions.append(
            (latitude, longitude)
        )

    for i, (lat, lon) in enumerate(true_positions, start=1):

        print(
            f"True point {i}: "
            f"{lat:.7f}, {lon:.7f}"
        )

    # ---------------------------------------------------------
    # 4. Add GNSS noise
    # ---------------------------------------------------------

    print("\n[4] Adding controlled GNSS noise...")

    noisy_positions = []

    for i, ((lat, lon), noise) in enumerate(
        zip(true_positions, NOISE_METERS),
        start=1,
    ):

        noisy_lat, noisy_lon = add_noise(
            lat,
            lon,
            noise,
            rng,
        )

        noisy_positions.append(
            (noisy_lat, noisy_lon)
        )

        actual_noise = haversine_distance_m(
            lat,
            lon,
            noisy_lat,
            noisy_lon,
        )

        print(
            f"State {i}: "
            f"noise={actual_noise:.2f} m"
        )

    # ---------------------------------------------------------
    # 5. Build NavigationState objects
    # ---------------------------------------------------------

    print("\n[5] Building navigation states...")

    from navigation_state import (
        NavigationState,
        NavigationMode,
    )

    navigation_states = []

    for i, (lat, lon) in enumerate(
        noisy_positions
    ):

        state = NavigationState(
            timestamp=float(i),
            latitude=lat,
            longitude=lon,
            altitude=0.0,
            vx=10.0,
            vy=0.0,
            yaw=0.0,
            covariance=[],
            mode=NavigationMode.DEAD_RECKONING,
        )

        navigation_states.append(state)

    print(
        f"Navigation states created : "
        f"{len(navigation_states)}"
    )

    # ---------------------------------------------------------
    # 6. Run map matcher
    # ---------------------------------------------------------

    print("\n[6] Running HMM map matcher...")

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    results = matcher.match(
        navigation_states
    )

    # ---------------------------------------------------------
    # 7. Calculate errors
    # ---------------------------------------------------------

    print("\n[7] Map-matching accuracy")

    noisy_errors = []
    snapped_errors = []

    for i, (
        true_position,
        noisy_position,
        result,
    ) in enumerate(
        zip(
            true_positions,
            noisy_positions,
            results,
        ),
        start=1,
    ):

        true_lat, true_lon = true_position
        noisy_lat, noisy_lon = noisy_position

        noisy_error = haversine_distance_m(
            true_lat,
            true_lon,
            noisy_lat,
            noisy_lon,
        )

        snapped_error = haversine_distance_m(
            true_lat,
            true_lon,
            result.lat_snapped,
            result.lon_snapped,
        )

        noisy_errors.append(noisy_error)
        snapped_errors.append(snapped_error)

        print("\n" + "-" * 60)
        print(f"State {i}")

        print(
            f"True road position : "
            f"{true_lat:.7f}, {true_lon:.7f}"
        )

        print(
            f"Noisy GPS          : "
            f"{noisy_lat:.7f}, {noisy_lon:.7f}"
        )

        print(
            f"Snapped position    : "
            f"{result.lat_snapped:.7f}, "
            f"{result.lon_snapped:.7f}"
        )

        print(
            f"Original GPS error  : "
            f"{noisy_error:.2f} m"
        )

        print(
            f"Snapped error       : "
            f"{snapped_error:.2f} m"
        )

        print(
            f"Confidence          : "
            f"{result.confidence_score:.6f}"
        )

        print(
            f"Road segment        : "
            f"{result.road_segment_id}"
        )

    # ---------------------------------------------------------
    # 8. Final benchmark
    # ---------------------------------------------------------

    average_noisy_error = (
        sum(noisy_errors)
        / len(noisy_errors)
    )

    average_snapped_error = (
        sum(snapped_errors)
        / len(snapped_errors)
    )

    improvement = (
        average_noisy_error
        - average_snapped_error
    )

    print("\n" + "=" * 80)
    print("FINAL ACCURACY RESULTS")
    print("=" * 80)

    print(
        f"Average original GPS error : "
        f"{average_noisy_error:.2f} m"
    )

    print(
        f"Average snapped error      : "
        f"{average_snapped_error:.2f} m"
    )

    print(
        f"Error improvement          : "
        f"{improvement:.2f} m"
    )

    if average_noisy_error > 0:
        improvement_percentage = (
            improvement
            / average_noisy_error
            * 100
        )

        print(
            f"Improvement percentage     : "
            f"{improvement_percentage:.2f}%"
        )

    print("=" * 80)
    print("REALISTIC TRAJECTORY TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()