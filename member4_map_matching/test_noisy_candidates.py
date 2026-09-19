"""
Member 4 - Noisy GNSS Candidate Diagnostic

Checks how many road candidates are available
for each noisy GNSS position.
"""

from osm_downloader import load_graph
from candidate_generator import generate_candidates


GRAPH_PATH = "data/osm/test_2km.graphml"


STATES = [
    {
        "latitude": 12.9720538,
        "longitude": 77.594311,
    },
    {
        "latitude": 12.97192,
        "longitude": 77.59498,
    },
    {
        "latitude": 12.97180,
        "longitude": 77.59560,
    },
    {
        "latitude": 12.97172,
        "longitude": 77.59622,
    },
    {
        "latitude": 12.97160,
        "longitude": 77.59685,
    },
]


print("=" * 80)
print()
print("# MEMBER 4 - NOISY GNSS CANDIDATE DIAGNOSTIC")
print()

graph = load_graph(GRAPH_PATH)

print()

for index, state in enumerate(STATES, start=1):

    candidates = generate_candidates(
        graph=graph,
        latitude=state["latitude"],
        longitude=state["longitude"],
        radius_m=30.0,
    )

    print("-" * 80)

    print(f"State {index}")

    print(
        f"GPS position : "
        f"{state['latitude']}, "
        f"{state['longitude']}"
    )

    print(
        f"Candidates   : "
        f"{len(candidates)}"
    )

    for candidate_index, candidate in enumerate(
        candidates,
        start=1,
    ):

        print(
            f"  Candidate {candidate_index}: "
            f"{candidate.distance_m:.2f} m"
        )

print("-" * 80)

print()
print("DIAGNOSTIC COMPLETED")
print()
print("=" * 80)