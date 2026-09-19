"""
Member 4 - HMM Transition Model

Calculates the probability of transitioning from one
road candidate to another between consecutive GPS states.

The transition model compares:

1. Network distance
2. Observed/driven distance

The network distance is calculated between the actual
snapped positions of the two candidates.
"""

import math

import networkx as nx
import osmnx as ox
from shapely.geometry import Point


DEFAULT_TRANSITION_SIGMA_M = 50.0


def get_projected_graph(graph):
    """
    Project the road graph once and cache it.

    Repeatedly projecting the complete OSM graph is expensive.
    This function stores the projected graph inside the original
    graph object so later calls can reuse it.
    """

    if "_member4_projected_graph" not in graph.graph:
        graph.graph["_member4_projected_graph"] = (
            ox.project_graph(graph)
        )

    return graph.graph["_member4_projected_graph"]


def haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate geographic distance between two coordinates.

    Returns:
        Distance in meters.
    """

    earth_radius_m = 6371000.0

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

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_m * c


def calculate_edge_position(
    graph,
    candidate,
) -> float:
    """
    Calculate the distance from the start node of the
    candidate edge to the candidate's snapped position.

    Returns:
        Distance in meters.
    """

    try:
        edge_data = graph.get_edge_data(
            candidate.u,
            candidate.v,
            candidate.key,
        )

        if edge_data is None:
            return 0.0

        geometry = edge_data.get("geometry")

        edge_length = float(
            edge_data.get("length", 0.0)
        )

        if geometry is None:
            return 0.0

        # --------------------------------------------------
        # Use cached projected graph.
        # This avoids repeatedly projecting the entire
        # OSM road network.
        # --------------------------------------------------

        projected_graph = get_projected_graph(graph)

        projected_edge_data = projected_graph.get_edge_data(
            candidate.u,
            candidate.v,
            candidate.key,
        )

        if projected_edge_data is None:
            return 0.0

        projected_geometry = projected_edge_data.get(
            "geometry"
        )

        if projected_geometry is None:
            return 0.0

        # Convert snapped GPS coordinate into projected point.
        projected_point = ox.projection.project_geometry(
            Point(
                candidate.snapped_longitude,
                candidate.snapped_latitude,
            ),
            crs="EPSG:4326",
            to_crs=projected_graph.graph["crs"],
        )[0]

        # Find position of snapped point along the road geometry.
        geometric_position = projected_geometry.project(
            projected_point
        )

        geometric_length = projected_geometry.length

        if geometric_length <= 0:
            return 0.0

        # Convert geometric position into a ratio along
        # the original OSM edge length.
        position_ratio = (
            geometric_position
            / geometric_length
        )

        position_ratio = max(
            0.0,
            min(1.0, position_ratio),
        )

        return position_ratio * edge_length

    except (
        nx.NodeNotFound,
        KeyError,
        AttributeError,
    ):
        return 0.0


def calculate_network_distance(
    graph,
    previous_candidate,
    current_candidate,
) -> float:
    """
    Calculate network distance between the actual
    snapped positions of two road candidates.

    The calculation is:

    previous snapped position
            ↓
    previous edge end
            ↓
    shortest road-network path
            ↓
    current edge start
            ↓
    current snapped position

    Returns:
        Network distance in meters.

        Infinity is returned if no valid network
        path exists.
    """

    try:

        # --------------------------------------------------
        # Case 1:
        # Both candidates are on the same directed edge.
        # --------------------------------------------------

        if (
            previous_candidate.u
            == current_candidate.u
            and previous_candidate.v
            == current_candidate.v
            and previous_candidate.key
            == current_candidate.key
        ):

            previous_position = calculate_edge_position(
                graph,
                previous_candidate,
            )

            current_position = calculate_edge_position(
                graph,
                current_candidate,
            )

            return abs(
                current_position
                - previous_position
            )

        # --------------------------------------------------
        # Position of previous candidate on its edge.
        # --------------------------------------------------

        previous_position = calculate_edge_position(
            graph,
            previous_candidate,
        )

        previous_edge_data = graph.get_edge_data(
            previous_candidate.u,
            previous_candidate.v,
            previous_candidate.key,
        )

        if previous_edge_data is None:
            return float("inf")

        previous_edge_length = float(
            previous_edge_data.get(
                "length",
                0.0,
            )
        )

        # Distance from previous snapped position
        # to the end of the previous edge.
        distance_to_previous_end = max(
            0.0,
            previous_edge_length
            - previous_position,
        )

        # --------------------------------------------------
        # Shortest path between the two road nodes.
        # --------------------------------------------------

        middle_distance = nx.shortest_path_length(
            graph,
            source=previous_candidate.v,
            target=current_candidate.u,
            weight="length",
        )

        # --------------------------------------------------
        # Position of current candidate on its edge.
        # --------------------------------------------------

        current_position = calculate_edge_position(
            graph,
            current_candidate,
        )

        # --------------------------------------------------
        # Total road-network distance.
        # --------------------------------------------------

        total_distance = (
            distance_to_previous_end
            + float(middle_distance)
            + current_position
        )

        return float(total_distance)

    except (
        nx.NetworkXNoPath,
        nx.NodeNotFound,
        KeyError,
        AttributeError,
    ):
        return float("inf")


def calculate_transition_probability(
    network_distance_m: float,
    observed_distance_m: float,
    sigma_m: float = DEFAULT_TRANSITION_SIGMA_M,
) -> float:
    """
    Calculate transition probability using the difference
    between network distance and observed distance.

    Smaller difference -> higher probability.

    Returns:
        Transition probability.
    """

    if sigma_m <= 0:
        raise ValueError(
            "sigma_m must be greater than zero."
        )

    # No valid road-network path.
    if math.isinf(network_distance_m):
        return 0.0

    difference = abs(
        network_distance_m
        - observed_distance_m
    )

    coefficient = 1.0 / (
        sigma_m
        * math.sqrt(2.0 * math.pi)
    )

    exponent = -(
        difference ** 2
    ) / (
        2.0 * sigma_m ** 2
    )

    return coefficient * math.exp(exponent)