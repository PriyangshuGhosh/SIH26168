"""HMM transition model (log-domain).

Equations
---------
Let d_obs be great-circle displacement between successive NavigationState
samples, and d_net the on-network path length between candidate endpoints.

    log P_trans = -0.5 * ((d_net - d_obs) / sigma_t)^2

Impossible network connectivity returns -inf (hard prune).

An optional heading-change term penalizes abrupt road-heading flips beyond
what the observed yaw change supports.
"""

from __future__ import annotations

from math import inf, pi

from .geometry import angular_difference_rad, haversine_m
from .road_graph import RoadNetwork, network_distance_m
from .types import NavigationState, RoadCandidate


def transition_log_probability(
    previous_state: NavigationState,
    current_state: NavigationState,
    previous_candidate: RoadCandidate,
    current_candidate: RoadCandidate,
    network: RoadNetwork,
    transition_sigma_m: float = 25.0,
) -> float:
    observed = haversine_m(
        previous_state.latitude,
        previous_state.longitude,
        current_state.latitude,
        current_state.longitude,
    )
    same = previous_candidate.road_segment_id == current_candidate.road_segment_id
    network_dist = network_distance_m(
        network,
        (previous_candidate.u_node, previous_candidate.v_node),
        (current_candidate.u_node, current_candidate.v_node),
        same_segment=same,
        observed_distance_m=observed,
    )
    if network_dist == inf:
        return -inf

    distance_score = -0.5 * ((network_dist - observed) / transition_sigma_m) ** 2

    road_turn = angular_difference_rad(
        previous_candidate.road_heading_rad,
        current_candidate.road_heading_rad,
    )
    yaw_turn = angular_difference_rad(previous_state.yaw_rad, current_state.yaw_rad)
    turn_sigma = 45.0 * pi / 180.0
    turn_score = -0.5 * ((road_turn - yaw_turn) / turn_sigma) ** 2
    return distance_score + 0.25 * turn_score
