from osm_downloader import load_graph
from navigation_state import NavigationState, NavigationMode
from viterbi import viterbi_map_match


GRAPH_PATH = "data/osm/test_2km.graphml"


def main():
    print("=" * 80)
    print("MEMBER 4 - VITERBI EDGE CASE TEST")
    print("=" * 80)

    graph = load_graph(GRAPH_PATH)

    # ---------------------------------------------------------
    # TEST 1 - Empty input
    # ---------------------------------------------------------
    print("\n[1] Testing empty navigation state list...")

    result = viterbi_map_match(
        graph=graph,
        gps_states=[],
    )

    assert result == ([], [], [])

    print("PASS - Empty input handled correctly.")

    # ---------------------------------------------------------
    # TEST 2 - No road candidates
    # ---------------------------------------------------------
    print("\n[2] Testing position with no road candidates...")

    far_away_state = NavigationState(
        timestamp=0.0,
        latitude=0.0,
        longitude=0.0,
        altitude=0.0,
        vx=0.0,
        vy=0.0,
        yaw=0.0,
        covariance=[],
        mode=NavigationMode.DEAD_RECKONING,
    )

    try:
        viterbi_map_match(
            graph=graph,
            gps_states=[far_away_state],
            candidate_radius_m=30.0,
        )

        raise AssertionError(
            "Expected ValueError for missing candidates."
        )

    except ValueError as error:
        print(f"PASS - Correctly rejected input: {error}")

    print("\n" + "=" * 80)
    print("VITERBI EDGE CASE TEST PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()