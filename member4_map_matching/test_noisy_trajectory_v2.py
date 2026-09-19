"""
Member 4 - Robust Noisy GNSS Trajectory Test

Creates noisy GNSS positions from actual road
geometry in the downloaded OSM graph.

This avoids manually selecting coordinates that
may fall outside the 30 m candidate radius.
"""

import math

from shapely.geometry import Point

from osm_downloader import load_graph
from map_match_engine import MapMatcher
from navigation_state import (
    NavigationState,
    NavigationMode,
)


GRAPH_PATH = "data/osm/test_2km.graphml"


# ---------------------------------------------------------
# Helper: convert projected road point back to latitude
# and longitude
# ---------------------------------------------------------

def projected_point_to_latlon(graph, point):
    """
    Convert a point from the projected graph CRS
    back to WGS84 latitude/longitude.
    """

    import osmnx as ox

    geometry = ox.projection.project_geometry(
        point,
        crs=graph.graph["crs"],
        to_crs="EPSG:4326",
    )[0]

    return geometry.y, geometry.x


# ---------------------------------------------------------
# 1. Load graph
# ---------------------------------------------------------

print("=" * 80)
print()
print("# MEMBER 4 - ROBUST NOISY GNSS TRAJECTORY TEST")
print()

print("[1] Loading offline OSM graph...")

graph = load_graph(GRAPH_PATH)

print()


# ---------------------------------------------------------
# 2. Select actual road points
# ---------------------------------------------------------

print("[2] Selecting positions directly from OSM roads...")

import osmnx as ox

projected_graph = ox.project_graph(graph)

edges = list(projected_graph.edges(keys=True, data=True))

# Select five road edges spread through the graph.
selected_edges = edges[::max(1, len(edges) // 5)][:5]

road_points = []

for u, v, key, data in selected_edges:

    geometry = data.get("geometry")

    if geometry is None:
        x = projected_graph.nodes[u]["x"]
        y = projected_graph.nodes[u]["y"]
        point = Point(x, y)
    else:
        point = geometry.interpolate(
            geometry.length * 0.5
        )

    latitude, longitude = projected_point_to_latlon(
        projected_graph,
        point,
    )

    road_points.append(
        (latitude, longitude)
    )


print(
    f"Road points selected : {len(road_points)}"
)

print()


# ---------------------------------------------------------
# 3. Add controlled GNSS noise
# ---------------------------------------------------------

print("[3] Adding controlled GNSS noise...")

# Approximate latitude/longitude conversion.
#
# 1 degree latitude ≈ 111,000 m
# Longitude conversion depends on latitude.

noise_meters = [
    5.0,
    8.0,
    10.0,
    12.0,
    15.0,
]


states = []

for index, (
    road_latitude,
    road_longitude,
) in enumerate(
    road_points
):

    noise = noise_meters[index]

    # Alternate noise direction so that the
    # points are displaced from the road.
    if index % 2 == 0:
        north_noise = noise
        east_noise = 0.0
    else:
        north_noise = 0.0
        east_noise = noise

    noisy_latitude = (
        road_latitude
        + north_noise / 111000.0
    )

    longitude_scale = (
        111000.0
        * math.cos(
            math.radians(road_latitude)
        )
    )

    noisy_longitude = (
        road_longitude
        + east_noise / longitude_scale
    )

    states.append(
        NavigationState(
            timestamp=float(index),
            latitude=noisy_latitude,
            longitude=noisy_longitude,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[
                [noise, 0.0],
                [0.0, noise],
            ],
            mode=NavigationMode.DEAD_RECKONING,
        )
    )

    print(
        f"State {index + 1}: "
        f"road=({road_latitude:.7f}, "
        f"{road_longitude:.7f}) "
        f"noise={noise:.1f} m"
    )


print()


# ---------------------------------------------------------
# 4. Run candidate generation check
# ---------------------------------------------------------

print("[4] Checking candidate availability...")

from candidate_generator import generate_candidates

all_candidates_available = True

for index, state in enumerate(
    states,
    start=1,
):

    candidates = generate_candidates(
        graph=graph,
        latitude=state.latitude,
        longitude=state.longitude,
        radius_m=30.0,
    )

    print(
        f"State {index}: "
        f"{len(candidates)} candidates"
    )

    if len(candidates) == 0:
        all_candidates_available = False


print()


if not all_candidates_available:

    print(
        "ERROR: One or more noisy positions have "
        "no candidates within 30 m."
    )

    print(
        "The test data needs adjustment."
    )

    raise SystemExit(1)


# ---------------------------------------------------------
# 5. Run HMM map matcher
# ---------------------------------------------------------

print("[5] Running HMM map matcher...")

matcher = MapMatcher(
    graph=graph,
    candidate_radius_m=30.0,
)

results = matcher.match(states)

print()


# ---------------------------------------------------------
# 6. Display results
# ---------------------------------------------------------

print("[6] Map-matching results")

print()

print("-" * 80)

for index, (
    state,
    result,
) in enumerate(
    zip(states, results),
    start=1,
):

    print(f"State {index}")

    print(
        f"Original noisy GPS : "
        f"{state.latitude:.7f}, "
        f"{state.longitude:.7f}"
    )

    print(
        f"Snapped position   : "
        f"{result.lat_snapped:.7f}, "
        f"{result.lon_snapped:.7f}"
    )

    print(
        f"Road segment       : "
        f"{result.road_segment_id}"
    )

    print(
        f"Confidence          : "
        f"{result.confidence_score:.6f}"
    )

    print(
        f"On road network     : "
        f"{result.is_on_road_network}"
    )

    print("-" * 80)


# ---------------------------------------------------------
# 7. Final validation
# ---------------------------------------------------------

all_on_road = all(
    result.is_on_road_network
    for result in results
)


print()

if all_on_road:

    print(
        "ROBUST NOISY GNSS MAP MATCHING TEST PASSED"
    )

else:

    print(
        "ROBUST NOISY GNSS MAP MATCHING TEST FAILED"
    )

print()

print("=" * 80)