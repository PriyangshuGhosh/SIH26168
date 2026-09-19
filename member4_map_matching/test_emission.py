"""
Member 4 - Emission probability test.

Loads the offline OSM graph, generates road candidates,
and calculates emission probabilities using a simulated
vehicle heading.
"""

import math

from osm_downloader import load_graph
from candidate_generator import generate_candidates
from emission_model import calculate_emission


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

GRAPH_PATH = "data/osm/test_2km.graphml"

GPS_LATITUDE = 12.9720
GPS_LONGITUDE = 77.5950

CANDIDATE_RADIUS_M = 30.0

# Simulated vehicle heading:
# 0 radians = North
VEHICLE_HEADING_RAD = 0.0


def main():

    print("=" * 70)
    print("MEMBER 4 - EMISSION PROBABILITY TEST")
    print("=" * 70)

    print("\nLoading offline OSM road graph...")

    graph = load_graph(
        GRAPH_PATH
    )

    print("\nGenerating road candidates...")

    candidates = generate_candidates(
        graph=graph,
        latitude=GPS_LATITUDE,
        longitude=GPS_LONGITUDE,
        radius_m=CANDIDATE_RADIUS_M,
    )

    print(
        f"Candidates found: "
        f"{len(candidates)}"
    )

    print(
        "\nVehicle heading: "
        f"{math.degrees(VEHICLE_HEADING_RAD):.1f} degrees"
    )

    print(
        "(0 degrees = North)"
    )

    print("\nEmission results:")

    results = []

    for candidate in candidates:

        result = calculate_emission(
            graph=graph,
            candidate=candidate,
            vehicle_heading_rad=VEHICLE_HEADING_RAD,
        )

        results.append(result)

    # -----------------------------------------------------
    # Sort by highest emission probability.
    # -----------------------------------------------------

    results.sort(
        key=lambda item: item["emission_probability"],
        reverse=True,
    )

    for index, result in enumerate(
        results,
        start=1,
    ):

        print("\n----------------------------------------")

        print(
            f"Candidate #{index}"
        )

        print(
            f"Road segment ID: "
            f"{result['road_segment_id']}"
        )

        print(
            f"Distance: "
            f"{result['distance_m']:.2f} m"
        )

        print(
            f"Road heading: "
            f"{math.degrees(result['road_heading_rad']):.2f} degrees"
        )

        print(
            f"Distance probability: "
            f"{result['distance_probability']:.8f}"
        )

        print(
            f"Heading probability: "
            f"{result['heading_probability']:.8f}"
        )

        print(
            f"Combined emission: "
            f"{result['emission_probability']:.10f}"
        )


if __name__ == "__main__":
    main()