"""
Member 4 - Member 3 Integration Test

Simulates the NavigationState objects that Member 3
will provide to the Member 4 map-matching engine.
"""

from osm_downloader import load_graph
from navigation_state import NavigationState, NavigationMode
from map_match_engine import MapMatcher


GRAPH_PATH = "data/osm/test_2km.graphml"


def main():
    print("=" * 90)
    print("MEMBER 4 - MEMBER 3 INTERFACE INTEGRATION TEST")
    print("=" * 90)

    print("\n[1] Loading offline OSM road graph...")

    graph = load_graph(GRAPH_PATH)

    print("\n[2] Creating Member 3-style NavigationState objects...")

    navigation_states = [
        NavigationState(
            timestamp=0.0,
            latitude=12.9720538,
            longitude=77.5943110,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[1.0, 0.0, 0.0, 1.0],
            mode=NavigationMode.GNSS_AIDED,
        ),
        NavigationState(
            timestamp=1.0,
            latitude=12.9711672,
            longitude=77.5972449,
            altitude=900.0,
            vx=15.0,
            vy=0.0,
            yaw=0.0,
            covariance=[1.0, 0.0, 0.0, 1.0],
            mode=NavigationMode.DEAD_RECKONING,
        ),
    ]

    print(f"Navigation states created: {len(navigation_states)}")

    for state_number, state in enumerate(
        navigation_states,
        start=1,
    ):
        print(
            f"State {state_number}: "
            f"lat={state.latitude}, "
            f"lon={state.longitude}, "
            f"mode={state.mode.value}"
        )

    print("\n[3] Creating Member 4 MapMatcher...")

    matcher = MapMatcher(
        graph=graph,
        candidate_radius_m=30.0,
    )

    print("MapMatcher created successfully.")

    print("\n[4] Running Member 3 -> Member 4 pipeline...")

    results = matcher.match(navigation_states)

    print(f"Results produced: {len(results)}")

    print("\n[5] FINAL OUTPUT")

    for index, result in enumerate(results, start=1):
        print("\n" + "-" * 70)
        print(f"State {index}")
        print(f"Timestamp          : {result.timestamp}")
        print(f"Snapped latitude   : {result.lat_snapped}")
        print(f"Snapped longitude  : {result.lon_snapped}")
        print(f"Road segment ID    : {result.road_segment_id}")
        print(f"Confidence         : {result.confidence_score}")
        print(
            f"On road network    : "
            f"{result.is_on_road_network}"
        )

    print("\n" + "=" * 90)
    print("MEMBER 3 -> MEMBER 4 INTEGRATION TEST PASSED")
    print("=" * 90)


if __name__ == "__main__":
    main()