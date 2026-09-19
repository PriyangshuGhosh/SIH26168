"""
Member 4 - Offline HMM Map Matching Engine

Public interface for the complete Member 4
map-matching pipeline.

Input:
    Member 3 NavigationState objects

Output:
    MapMatchedPosition objects
"""

from candidate_generator import generate_candidates
from map_match_output import (
    calculate_confidence,
    create_map_matched_position,
)
from navigation_state import NavigationState
from viterbi import viterbi_map_match


class MapMatcher:
    """
    Offline HMM map-matching engine.

    The engine consumes NavigationState objects
    and returns map-matched road positions.
    """

    def __init__(
        self,
        graph,
        candidate_radius_m=30.0,
    ):
        if graph is None:
            raise ValueError(
                "OSM road graph cannot be None."
            )

        if candidate_radius_m <= 0:
            raise ValueError(
                "Candidate radius must be greater than zero."
            )

        self.graph = graph
        self.candidate_radius_m = candidate_radius_m

    def match(
        self,
        navigation_states,
    ):
        """
        Map-match a sequence of NavigationState objects.

        Parameters
        ----------
        navigation_states:
            List of Member 3 NavigationState objects.

        Returns
        -------
        list[MapMatchedPosition]
            Final map-matched positions.
        """

        if not navigation_states:
            return []

        for state in navigation_states:
            if not isinstance(
                state,
                NavigationState,
            ):
                raise TypeError(
                    "All inputs must be NavigationState objects."
                )

        (
            best_sequence,
            scores,
            all_candidates,
        ) = viterbi_map_match(
            graph=self.graph,
            gps_states=navigation_states,
            candidate_radius_m=self.candidate_radius_m,
        )

        results = []

        for t, (
            candidate,
            navigation_state,
        ) in enumerate(
            zip(
                best_sequence,
                navigation_states,
            )
        ):

            selected_index = (
                all_candidates[t].index(
                    candidate
                )
            )

            confidence = calculate_confidence(
                state_scores=scores[t],
                selected_index=selected_index,
            )

            result = create_map_matched_position(
                graph=self.graph,
                candidate=candidate,
                gps_state=navigation_state,
                confidence_score=confidence,
            )

            results.append(result)

        return results