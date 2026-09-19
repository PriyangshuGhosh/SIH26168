"""
Member 4 - Optimized Road Candidate Generator

Finds OSM road segments within a configurable radius
around a drifting GPS/NavigationState position.

Optimization:
The road network is converted and projected only once.
Subsequent candidate searches reuse the prepared data.
"""

from dataclasses import dataclass
from typing import Any
import math

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point
from shapely.ops import nearest_points


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

DEFAULT_CANDIDATE_RADIUS_M = 30.0


# ---------------------------------------------------------
# Data structure
# ---------------------------------------------------------

@dataclass
class RoadCandidate:
    u: Any
    v: Any
    key: Any

    road_segment_id: Any

    snapped_latitude: float
    snapped_longitude: float

    distance_m: float

    highway: Any = None


# ---------------------------------------------------------
# Coordinate helper
# ---------------------------------------------------------

def haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:

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
# Prepare graph
# ---------------------------------------------------------

def prepare_candidate_graph(graph):
    """
    Prepare the OSM graph once for repeated candidate searches.

    The prepared data is stored inside graph.graph so that
    multiple calls to generate_candidates() can reuse it.
    """

    cache_key = "_member4_candidate_edges_projected"

    if cache_key in graph.graph:

        return graph.graph[cache_key]

    print("Preparing road network for candidate search...")

    # Convert graph to edge GeoDataFrame once.
    _, edges_gdf = ox.convert.graph_to_gdfs(
        graph,
        nodes=True,
        edges=True,
    )

    if edges_gdf.empty:

        prepared = (
            edges_gdf,
            None,
        )

        graph.graph[cache_key] = prepared

        return prepared

    # Project road network to metric CRS once.
    projected_crs = edges_gdf.estimate_utm_crs()

    edges_projected = edges_gdf.to_crs(
        projected_crs
    )

    prepared = (
        edges_projected,
        projected_crs,
    )

    graph.graph[cache_key] = prepared

    print(
        "Candidate search preparation completed."
    )

    return prepared


# ---------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------

def generate_candidates(
    graph,
    latitude: float,
    longitude: float,
    radius_m: float = DEFAULT_CANDIDATE_RADIUS_M,
):
    """
    Find road segments within radius_m of a GPS position.

    The road network is prepared only once.
    """

    if radius_m <= 0:

        raise ValueError(
            "Candidate radius must be greater than 0."
        )

    # -----------------------------------------------------
    # Reuse prepared road network.
    # -----------------------------------------------------

    (
        edges_projected,
        projected_crs,
    ) = prepare_candidate_graph(graph)

    if edges_projected.empty:

        return []

    # -----------------------------------------------------
    # Convert GPS point to projected metric coordinates.
    # -----------------------------------------------------

    gps_point = gpd.GeoDataFrame(
        geometry=[
            Point(
                longitude,
                latitude,
            )
        ],
        crs="EPSG:4326",
    )

    gps_projected = gps_point.to_crs(
        projected_crs
    )

    gps_geometry = (
        gps_projected.geometry.iloc[0]
    )

    # -----------------------------------------------------
    # Spatial search area.
    # -----------------------------------------------------

    search_box = gps_geometry.buffer(
        radius_m
    )

    possible_edges = edges_projected[
        edges_projected.geometry.intersects(
            search_box
        )
    ]

    candidates = []

    # -----------------------------------------------------
    # Examine possible road segments.
    # -----------------------------------------------------

    for index, edge in possible_edges.iterrows():

        geometry = edge.geometry

        if geometry is None:

            continue

        # -------------------------------------------------
        # Find closest point ON THE ROAD.
        # -------------------------------------------------

        _, snapped_point = nearest_points(
            gps_geometry,
            geometry,
        )

        # -------------------------------------------------
        # Exact distance.
        # -------------------------------------------------

        distance_m = gps_geometry.distance(
            geometry
        )

        if distance_m > radius_m:

            continue

        # -------------------------------------------------
        # Convert snapped point back to WGS84.
        # -------------------------------------------------

        snapped_gdf = gpd.GeoDataFrame(
            geometry=[
                snapped_point
            ],
            crs=projected_crs,
        )

        snapped_wgs84 = (
            snapped_gdf.to_crs(
                "EPSG:4326"
            )
        )

        snapped_geometry = (
            snapped_wgs84.geometry.iloc[0]
        )

        snapped_lon = (
            snapped_geometry.x
        )

        snapped_lat = (
            snapped_geometry.y
        )

        # -------------------------------------------------
        # Edge identifier.
        # -------------------------------------------------

        u = index[0]
        v = index[1]
        key = index[2]

        road_segment_id = edge.get(
            "osmid",
            f"{u}-{v}-{key}",
        )

        highway = edge.get(
            "highway",
            None,
        )

        candidate = RoadCandidate(
            u=u,
            v=v,
            key=key,
            road_segment_id=road_segment_id,
            snapped_latitude=snapped_lat,
            snapped_longitude=snapped_lon,
            distance_m=float(distance_m),
            highway=highway,
        )

        candidates.append(
            candidate
        )

    # -----------------------------------------------------
    # Nearest candidates first.
    # -----------------------------------------------------

    candidates.sort(
        key=lambda candidate:
        candidate.distance_m
    )

    return candidates