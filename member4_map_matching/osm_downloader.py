"""
Member 4 - OpenStreetMap road network downloader.

Downloads a driving-road graph from OpenStreetMap using OSMnx
and the Overpass API.

The graph can later be saved locally and reused offline.
"""

from pathlib import Path

import osmnx as ox


DEFAULT_RADIUS_M = 2000


def download_road_network(
    latitude: float,
    longitude: float,
    radius_m: float = DEFAULT_RADIUS_M,
):
    """
    Download a driving-road network around a coordinate.

    Parameters
    ----------
    latitude : float
        Center latitude.

    longitude : float
        Center longitude.

    radius_m : float
        Search radius in meters.

    Returns
    -------
    networkx.MultiDiGraph
        OSM road network.
    """

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    if radius_m <= 0:
        raise ValueError("Radius must be greater than 0 meters.")

    print("Downloading OpenStreetMap road network...")
    print(f"Center : ({latitude}, {longitude})")
    print(f"Radius : {radius_m} meters")

    graph = ox.graph.graph_from_point(
        center_point=(latitude, longitude),
        dist=radius_m,
        dist_type="bbox",
        network_type="drive",
        simplify=True,
        retain_all=False,
    )

    print("\nOSM download completed.")
    print(f"Nodes : {len(graph.nodes)}")
    print(f"Edges : {len(graph.edges)}")

    return graph


def save_graph(graph, output_path: str):
    """
    Save an OSM graph locally as GraphML.
    """

    output_file = Path(output_path)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ox.io.save_graphml(
        graph,
        filepath=output_file,
    )

    print(f"\nGraph saved to: {output_file}")


def load_graph(input_path: str):
    """
    Load a previously downloaded graph.

    This is the beginning of the offline-processing pipeline.
    """

    graph = ox.io.load_graphml(input_path)

    print(f"Loaded graph from: {input_path}")
    print(f"Nodes : {len(graph.nodes)}")
    print(f"Edges : {len(graph.edges)}")

    return graph


if __name__ == "__main__":

    # Example coordinate.
    # Replace this with the coordinate supplied by Member 3.

    LATITUDE = 12.9716
    LONGITUDE = 77.5946

    # 2 km radius.
    RADIUS_M = 2000

    graph = download_road_network(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        radius_m=RADIUS_M,
    )

    save_graph(
        graph,
        "data/osm/bangalore_2km.graphml",
    )