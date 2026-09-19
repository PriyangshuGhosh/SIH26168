from osm_downloader import load_graph
from candidate_generator import generate_candidates


GRAPH_PATH = "data/osm/test_2km.graphml"

# One of the noisy points from the previous test
LATITUDE = 12.9885908
LONGITUDE = 77.6031563


print("=" * 70)
print("MEMBER 4 - GEOMETRIC SNAPPING DIAGNOSTIC")
print("=" * 70)

print("\n[1] Loading graph...")

graph = load_graph(GRAPH_PATH)

print("\n[2] Generating candidates...")

candidates = generate_candidates(
    graph=graph,
    latitude=LATITUDE,
    longitude=LONGITUDE,
    radius_m=30.0,
)

print(f"\nCandidates found: {len(candidates)}")

for i, candidate in enumerate(candidates, start=1):

    print("\n" + "-" * 60)

    print(f"Candidate {i}")

    print(
        f"Road segment      : "
        f"{candidate.road_segment_id}"
    )

    print(
        f"Original GPS      : "
        f"{LATITUDE:.10f}, {LONGITUDE:.10f}"
    )

    print(
        f"Snapped position  : "
        f"{candidate.snapped_latitude:.10f}, "
        f"{candidate.snapped_longitude:.10f}"
    )

    print(
        f"Distance          : "
        f"{candidate.distance_m:.6f} m"
    )

    print(
        f"Difference lat    : "
        f"{candidate.snapped_latitude - LATITUDE:.10f}"
    )

    print(
        f"Difference lon    : "
        f"{candidate.snapped_longitude - LONGITUDE:.10f}"
    )

print("\n" + "=" * 70)
print("SNAPPING DIAGNOSTIC COMPLETED")
print("=" * 70)