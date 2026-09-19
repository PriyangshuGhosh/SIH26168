"""
Member 4 - Viterbi HMM Map Matching

Combines:

1. Candidate generation
2. Emission probabilities
3. Transition probabilities

to determine the most likely road sequence.

Supports:

1. Dictionary-based GPS states
2. Member 3 NavigationState dataclass
"""

import math

from candidate_generator import generate_candidates
from emission_model import calculate_emission
from transition_model import (
    calculate_network_distance,
    calculate_transition_probability,
    haversine_distance_m,
)
from navigation_state import NavigationState


def get_state_value(state, key):
    """
    Read a navigation-state value from either:

    1. A NavigationState dataclass
    2. A dictionary

    Member 3 uses:

        yaw

    for vehicle heading.

    The current test dictionaries use:

        heading

    This helper allows both formats to work.
    """

    if isinstance(state, NavigationState):

        if key == "heading":
            return state.yaw

        return getattr(state, key)

    return state[key]


def viterbi_map_match(
    graph,
    gps_states,
    candidate_radius_m=30.0,
):
    """
    Perform HMM Viterbi map matching.

    Parameters
    ----------
    graph:
        Offline OSM road graph.

    gps_states:
        List of GPS states.

        Supported formats:

        Dictionary:
            {
                "timestamp": ...,
                "latitude": ...,
                "longitude": ...,
                "heading": ...
            }

        NavigationState:
            timestamp
            latitude
            longitude
            altitude
            vx
            vy
            yaw
            covariance
            mode

    candidate_radius_m:
        Candidate search radius in meters.

    Returns
    -------
    tuple
        (
            best_sequence,
            scores,
            all_candidates
        )

    best_sequence:
        Most likely road candidate sequence.

    scores:
        Viterbi scores for every candidate
        at every GPS state.

    all_candidates:
        Candidate list for every GPS state.
    """

    # ---------------------------------------------------------
    # STEP 0 - VALIDATE INPUT
    # ---------------------------------------------------------

    if not gps_states:
        return [], [], []

    if graph is None:
        raise ValueError(
            "OSM road graph cannot be None."
        )

    # ---------------------------------------------------------
    # STEP 1 - GENERATE ROAD CANDIDATES
    # ---------------------------------------------------------

    all_candidates = []

    for state in gps_states:

        latitude = get_state_value(
            state,
            "latitude",
        )

        longitude = get_state_value(
            state,
            "longitude",
        )

        candidates = generate_candidates(
            graph=graph,
            latitude=latitude,
            longitude=longitude,
            radius_m=candidate_radius_m,
        )

        all_candidates.append(
            candidates
        )

    # Make sure every GPS state has candidates.
    if any(
        len(candidates) == 0
        for candidates in all_candidates
    ):
        raise ValueError(
            "At least one GPS state has no road candidates."
        )

    # ---------------------------------------------------------
    # STEP 2 - INITIALIZATION
    # ---------------------------------------------------------

    scores = []
    backpointers = []

    first_candidates = all_candidates[0]

    first_scores = []

    first_heading = get_state_value(
        gps_states[0],
        "heading",
    )

    for candidate in first_candidates:

        # -----------------------------------------------------
        # Calculate emission probability
        # -----------------------------------------------------

        emission_result = calculate_emission(
            graph=graph,
            candidate=candidate,
            vehicle_heading_rad=first_heading,
        )

        emission_probability = emission_result[
            "emission_probability"
        ]

        # Prevent log(0)
        emission_probability = max(
            emission_probability,
            1e-300,
        )

        # Convert probability to log probability.
        score = math.log(
            emission_probability
        )

        first_scores.append(
            score
        )

    scores.append(
        first_scores
    )

    backpointers.append(
        [None] * len(first_candidates)
    )

    # ---------------------------------------------------------
    # STEP 3 - VITERBI RECURSION
    # ---------------------------------------------------------

    for t in range(
        1,
        len(gps_states),
    ):

        current_candidates = all_candidates[t]

        previous_candidates = all_candidates[t - 1]

        current_scores = []

        current_backpointers = []

        # -----------------------------------------------------
        # Calculate observed GPS movement
        # -----------------------------------------------------

        previous_latitude = get_state_value(
            gps_states[t - 1],
            "latitude",
        )

        previous_longitude = get_state_value(
            gps_states[t - 1],
            "longitude",
        )

        current_latitude = get_state_value(
            gps_states[t],
            "latitude",
        )

        current_longitude = get_state_value(
            gps_states[t],
            "longitude",
        )

        observed_distance = haversine_distance_m(
            previous_latitude,
            previous_longitude,
            current_latitude,
            current_longitude,
        )

        current_heading = get_state_value(
            gps_states[t],
            "heading",
        )

        # -----------------------------------------------------
        # Evaluate every current candidate
        # -----------------------------------------------------

        for current_candidate in current_candidates:

            # -------------------------------------------------
            # Emission probability
            # -------------------------------------------------

            emission_result = calculate_emission(
                graph=graph,
                candidate=current_candidate,
                vehicle_heading_rad=current_heading,
            )

            emission_probability = emission_result[
                "emission_probability"
            ]

            # Prevent log(0)
            emission_probability = max(
                emission_probability,
                1e-300,
            )

            emission_log = math.log(
                emission_probability
            )

            # -------------------------------------------------
            # Find best previous candidate
            # -------------------------------------------------

            best_score = -math.inf

            best_previous_index = None

            for previous_index, previous_candidate in enumerate(
                previous_candidates
            ):

                # -------------------------------------------------
                # Network distance
                # -------------------------------------------------

                network_distance = (
                    calculate_network_distance(
                        graph,
                        previous_candidate,
                        current_candidate,
                    )
                )

                # No valid road-network path.
                if math.isinf(
                    network_distance
                ):
                    continue

                # -------------------------------------------------
                # Transition probability
                # -------------------------------------------------

                transition_probability = (
                    calculate_transition_probability(
                        network_distance_m=network_distance,
                        observed_distance_m=observed_distance,
                    )
                )

                # Prevent log(0)
                transition_probability = max(
                    transition_probability,
                    1e-300,
                )

                transition_log = math.log(
                    transition_probability
                )

                # -------------------------------------------------
                # Viterbi score
                # -------------------------------------------------

                total_score = (
                    scores[t - 1][previous_index]
                    + transition_log
                    + emission_log
                )

                # -------------------------------------------------
                # Keep best previous candidate
                # -------------------------------------------------

                if total_score > best_score:

                    best_score = total_score

                    best_previous_index = (
                        previous_index
                    )

            current_scores.append(
                best_score
            )

            current_backpointers.append(
                best_previous_index
            )

        scores.append(
            current_scores
        )

        backpointers.append(
            current_backpointers
        )

    # ---------------------------------------------------------
    # STEP 4 - BACKTRACK
    # ---------------------------------------------------------

    last_scores = scores[-1]

    # Make sure at least one valid path exists.
    if all(
        math.isinf(score)
        for score in last_scores
    ):
        raise ValueError(
            "Viterbi could not find a valid road path."
        )

    # Find candidate with the highest final Viterbi score.
    best_last_index = max(
        range(len(last_scores)),
        key=lambda i: last_scores[i],
    )

    best_sequence_indices = [
        best_last_index
    ]

    # Walk backwards through the backpointers.
    for t in range(
        len(gps_states) - 1,
        0,
        -1,
    ):

        current_index = (
            best_sequence_indices[-1]
        )

        previous_index = backpointers[t][
            current_index
        ]

        if previous_index is None:
            break

        best_sequence_indices.append(
            previous_index
        )

    # Reverse because we backtracked
    # from the final state.
    best_sequence_indices.reverse()

    # ---------------------------------------------------------
    # STEP 5 - BUILD BEST ROAD SEQUENCE
    # ---------------------------------------------------------

    best_sequence = []

    for t, candidate_index in enumerate(
        best_sequence_indices
    ):

        candidate = all_candidates[t][
            candidate_index
        ]

        best_sequence.append(
            candidate
        )

    # ---------------------------------------------------------
    # STEP 6 - RETURN RESULTS
    # ---------------------------------------------------------

    return (
        best_sequence,
        scores,
        all_candidates,
    )