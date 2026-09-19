"""
Member 4 - Basic OSM map matcher.

This is the first prototype before implementing
the full HMM + Viterbi algorithm.
"""

import math

import osmnx as ox


def calculate_heading(
    lat1,
    lon1,
    lat2,
    lon2,
):
    """
    Calculate approximate heading between two coordinates.
    """

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    delta_lon = math.radians(lon2 - lon1)

    x = math.sin(delta_lon) * math.cos(lat2)

    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1)
        * math.cos(lat2)
        * math.cos(delta_lon)
    )

    heading = math.atan2(x, y)

    return heading % (2 * math.pi)


def find_nearest_road(
    graph,
    latitude,
    longitude,
):
    """
    Find the nearest OSM road segment to a GPS coordinate.
    """

    edge = ox.distance.nearest_edges(
        graph,
        X=longitude,
        Y=latitude,
    )

    u, v, key = edge

    edge_data = graph.edges[u, v, key]

    geometry = edge_data.get("geometry")

    if geometry is not None:

        midpoint = geometry.interpolate(
            geometry.length / 2
        )

        snapped_lon = midpoint.x
        snapped_lat = midpoint.y

    else:

        snapped_lat = (
            graph.nodes[u]["y"]
            + graph.nodes[v]["y"]
        ) / 2

        snapped_lon = (
            graph.nodes[u]["x"]
            + graph.nodes[v]["x"]
        ) / 2

    road_segment_id = edge_data.get(
        "osmid",
        f"{u}-{v}",
    )

    return {
        "lat_snapped": snapped_lat,
        "lon_snapped": snapped_lon,
        "road_segment_id": road_segment_id,
        "is_on_road_network": True,
    }