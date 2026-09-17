"""HMM emission model (log-domain).

Equations
---------
Let d be perpendicular distance (m) from the observation to the candidate
road, and sigma_p the position uncertainty (m) from Member 3 covariance.

    log P_pos = -0.5 * (d / sigma_p)^2

Let Delta_psi be the smallest absolute heading error (rad) between the
vehicle yaw and the road heading. If heading is invalid/degraded, the
heading term is skipped (weight 0) rather than forcing agreement.

    log P_hdg = -0.5 * (Delta_psi / sigma_psi)^2

    log emission = log P_pos + w_hdg * log P_hdg

Large sigma_p flattens the emission surface: map matching must not invent
precise global position when input uncertainty is large.
"""

from __future__ import annotations

from math import pi

from .geometry import angular_difference_rad
from .types import NavigationState, RoadCandidate


def emission_log_probability(
    state: NavigationState,
    candidate: RoadCandidate,
    heading_sigma_rad: float = 30.0 * pi / 180.0,
    heading_weight: float = 1.0,
) -> float:
    sigma_p = state.position_sigma_m
    position_score = -0.5 * (candidate.distance_m / sigma_p) ** 2

    if not state.heading_valid or heading_weight <= 0.0:
        return position_score

    # Roads are directed; also allow opposite heading for undirected ambiguity
    # by taking the min error against heading and heading+pi, then prefer
    # the directed road heading via a mild extra cost on reverse.
    err_fwd = angular_difference_rad(state.yaw_rad, candidate.road_heading_rad)
    err_rev = angular_difference_rad(state.yaw_rad, candidate.road_heading_rad + pi)
    if err_fwd <= err_rev:
        heading_error = err_fwd
        reverse_penalty = 0.0
    else:
        heading_error = err_rev
        reverse_penalty = 1.5  # discourage reverse travel when forward exists

    heading_score = -0.5 * (heading_error / heading_sigma_rad) ** 2 - reverse_penalty
    return position_score + heading_weight * heading_score
