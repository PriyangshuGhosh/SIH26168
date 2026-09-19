"""
Member 4 - Offline OSM graph test.

Loads a previously downloaded OSM road graph
without accessing the internet.
"""

from osm_downloader import load_graph
from map_matcher import find_nearest_road


GRAPH_PATH = "data/osm/test_2km.graphml"


def main():

    print("=" * 60)
    print("MEMBER 4 - OFFLINE MAP MATCHING TEST")
    print("=" * 60)

    print("\nLoading locally saved OSM graph...")

    graph = load_graph(GRAPH_PATH)

    # Simulated drifting GPS position
    gps_latitude = 12.9720
    gps_longitude = 77.5950

    print("\nInput GPS position:")
    print(f"Latitude  : {gps_latitude}")
    print(f"Longitude : {gps_longitude}")

    result = find_nearest_road(
        graph,
        gps_latitude,
        gps_longitude,
    )

    print("\nMap-matched result:")

    print(
        f"Snapped latitude  : "
        f"{result['lat_snapped']}"
    )

    print(
        f"Snapped longitude : "
        f"{result['lon_snapped']}"
    )

    print(
        f"Road segment ID   : "
        f"{result['road_segment_id']}"
    )

    print(
        f"On road network   : "
        f"{result['is_on_road_network']}"
    )


if __name__ == "__main__":
    main()