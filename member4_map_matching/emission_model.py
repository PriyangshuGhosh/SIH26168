"""
Member 4 - HMM Emission Model

Calculates how likely a road candidate is for a
given NavigationState.

Current factors:
1. Perpendicular distance from GPS position to road
2. Heading compatibility between vehicle and road

The resulting score will later be used by the HMM.
"""

import math
from typing import Any


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

DEFAULT_DISTANCE_SIGMA_M = 10.0
DEFAULT_HEADING_SIGMA_RAD = math.radians(30.0)


# ---------------------------------------------------------
# Angle utilities
# ---------------------------------------------------------

def normalize_angle(angle_rad: float) -> float:
    """
    Normalize angle to the range [-pi, pi].
    """

    return (
        angle_rad + math.pi
    ) % (
        2 * math.pi
    ) - math.pi


def angular_difference(
    angle1_rad: float,
    angle2_rad: float,
) -> float:
    """
    Calculate the smallest heading difference while treating
    opposite directions on the same road as equivalent.

    Example:

    Vehicle heading = 0°
    Road heading    = 180°

    Normal difference = 180°
    Bidirectional road difference = 0°
    """

    difference = normalize_angle(
        angle1_rad - angle2_rad
    )

    difference = abs(difference)

    # Roads can normally be travelled in either direction.
    # Therefore, 180° should be treated as equivalent to 0°.
    difference = min(
        difference,
        math.pi - difference,
    )

    return difference

# ---------------------------------------------------------
# Gaussian probability
# ---------------------------------------------------------

def gaussian_probability(
    error: float,
    sigma: float,
) -> float:
    """
    Gaussian probability density.

    Parameters
    ----------
    error:
        Measurement error.

    sigma:
        Standard deviation.

    Returns
    -------
    float
        Probability density.
    """

    if sigma <= 0:
        raise ValueError(
            "Sigma must be greater than zero."
        )

    coefficient = 1.0 / (
        sigma * math.sqrt(2.0 * math.pi)
    )

    exponent = -(
        error ** 2
    ) / (
        2.0 * sigma ** 2
    )

    return coefficient * math.exp(exponent)


# ---------------------------------------------------------
# Distance emission
# ---------------------------------------------------------

def distance_emission_probability(
    distance_m: float,
    sigma_m: float = DEFAULT_DISTANCE_SIGMA_M,
) -> float:
    """
    Calculate Gaussian emission probability based
    on perpendicular distance from GPS position
    to the road segment.
    """

    return gaussian_probability(
        error=distance_m,
        sigma=sigma_m,
    )


# ---------------------------------------------------------
# Road heading
# ---------------------------------------------------------

def calculate_bearing(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    """
    Calculate bearing from point 1 to point 2.

    Returns radians where:

        0       = North
        pi/2    = East
        pi      = South
        -pi/2   = West
    """

    lat1 = math.radians(latitude1)
    lat2 = math.radians(latitude2)

    delta_lon = math.radians(
        longitude2 - longitude1
    )

    x = (
        math.sin(delta_lon)
        * math.cos(lat2)
    )

    y = (
        math.cos(lat1)
        * math.sin(lat2)
        -
        math.sin(lat1)
        * math.cos(lat2)
        * math.cos(delta_lon)
    )

    return math.atan2(x, y)


def get_candidate_heading(
    graph,
    candidate,
) -> float:
    """
    Calculate the heading of an OSM road candidate.

    Uses the direction from the candidate's
    start node to its end node.
    """

    start_node = graph.nodes[
        candidate.u
    ]

    end_node = graph.nodes[
        candidate.v
    ]

    return calculate_bearing(
        latitude1=start_node["y"],
        longitude1=start_node["x"],
        latitude2=end_node["y"],
        longitude2=end_node["x"],
    )


# ---------------------------------------------------------
# Heading probability
# ---------------------------------------------------------

def heading_emission_probability(
    vehicle_heading_rad: float,
    road_heading_rad: float,
    sigma_rad: float = DEFAULT_HEADING_SIGMA_RAD,
) -> float:
    """
    Calculate heading compatibility.

    A smaller angular difference gives a higher probability.
    """

    difference = angular_difference(
        vehicle_heading_rad,
        road_heading_rad,
    )

    return gaussian_probability(
        error=difference,
        sigma=sigma_rad,
    )


# ---------------------------------------------------------
# Combined emission
# ---------------------------------------------------------

def calculate_emission(
    graph,
    candidate,
    vehicle_heading_rad: float,
    distance_sigma_m: float = DEFAULT_DISTANCE_SIGMA_M,
    heading_sigma_rad: float = DEFAULT_HEADING_SIGMA_RAD,
) -> dict[str, Any]:
    """
    Calculate the complete emission information
    for one road candidate.
    """

    road_heading = get_candidate_heading(
        graph,
        candidate,
    )

    distance_probability = (
        distance_emission_probability(
            distance_m=candidate.distance_m,
            sigma_m=distance_sigma_m,
        )
    )

    heading_probability = (
        heading_emission_probability(
            vehicle_heading_rad=vehicle_heading_rad,
            road_heading_rad=road_heading,
            sigma_rad=heading_sigma_rad,
        )
    )

    # Combine both independent observation factors.
    combined_probability = (
        distance_probability
        * heading_probability
    )

    return {
        "road_segment_id": candidate.road_segment_id,
        "distance_m": candidate.distance_m,
        "road_heading_rad": road_heading,
        "distance_probability": distance_probability,
        "heading_probability": heading_probability,
        "emission_probability": combined_probability,
    }