"""Sliding-window offline HMM map matcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .candidates import generate_candidates, search_radius_m
from .road_graph import RoadNetwork, load_network
from .spatial_index import SpatialIndex
from .types import MapMatchedPosition, NavigationState, RoadCandidate
from .viterbi import candidate_confidence, viterbi_decode


@dataclass
class MapMatcherConfig:
    base_search_radius_m: float = 30.0
    max_candidates: int = 12
    window_size: int = 8
    on_road_confidence_min: float = 0.35
    on_road_distance_max_m: float = 25.0
    # Reject forced snaps when uncertainty dwarfs the distance signal
    max_sigma_for_forced_on_road_m: float = 40.0


@dataclass
class MapMatcher:
    network: RoadNetwork
    config: MapMatcherConfig = field(default_factory=MapMatcherConfig)
    _index: SpatialIndex = field(init=False)
    _window_states: list[NavigationState] = field(default_factory=list, init=False)
    _window_candidates: list[list[RoadCandidate]] = field(
        default_factory=list, init=False
    )

    def __post_init__(self) -> None:
        self._index = SpatialIndex(self.network)

    @classmethod
    def from_path(
        cls, path: Path | str, config: MapMatcherConfig | None = None
    ) -> "MapMatcher":
        return cls(load_network(Path(path)), config or MapMatcherConfig())

    def reset(self) -> None:
        self._window_states.clear()
        self._window_candidates.clear()

    def match(self, state: NavigationState) -> MapMatchedPosition:
        """Online step: append observation, run sliding-window Viterbi, emit latest."""
        cands = generate_candidates(
            state,
            self.network,
            self._index,
            base_radius_m=self.config.base_search_radius_m,
            max_candidates=self.config.max_candidates,
        )
        self._window_states.append(state)
        self._window_candidates.append(cands)
        if len(self._window_states) > self.config.window_size:
            self._window_states.pop(0)
            self._window_candidates.pop(0)

        path, _ = viterbi_decode(
            self._window_states, self._window_candidates, self.network
        )
        matched = path[-1] if path else None
        return self._to_output(state, matched, cands)

    def match_trajectory(
        self, states: list[NavigationState]
    ) -> list[MapMatchedPosition]:
        """Batch offline decode (full sequence Viterbi, not independent snaps)."""
        self.reset()
        candidate_sets = [
            generate_candidates(
                s,
                self.network,
                self._index,
                base_radius_m=self.config.base_search_radius_m,
                max_candidates=self.config.max_candidates,
            )
            for s in states
        ]
        path, _ = viterbi_decode(states, candidate_sets, self.network)
        return [
            self._to_output(s, m, cands)
            for s, m, cands in zip(states, path, candidate_sets)
        ]

    def nearest_road_baseline(
        self, states: list[NavigationState]
    ) -> list[MapMatchedPosition]:
        """Independent nearest-road baseline (for accuracy comparison only)."""
        outputs = []
        for state in states:
            cands = generate_candidates(
                state,
                self.network,
                self._index,
                base_radius_m=self.config.base_search_radius_m,
                max_candidates=self.config.max_candidates,
            )
            matched = cands[0] if cands else None
            outputs.append(self._to_output(state, matched, cands))
        return outputs

    def _to_output(
        self,
        state: NavigationState,
        matched: RoadCandidate | None,
        candidates: list[RoadCandidate],
    ) -> MapMatchedPosition:
        if matched is None:
            return MapMatchedPosition(
                timestamp=state.timestamp,
                lat_snapped=state.latitude,
                lon_snapped=state.longitude,
                heading_snapped_rad=state.yaw_rad,
                road_segment_id=0,
                confidence_score=0.0,
                is_on_road_network=False,
                distance_to_road_m=search_radius_m(
                    state, self.config.base_search_radius_m
                ),
            )

        confidence = candidate_confidence(state, matched, candidates)
        # Soften confidence when uncertainty is large relative to geometry
        sigma = state.position_sigma_m
        if sigma > 10.0:
            confidence *= 10.0 / sigma

        on_road = (
            confidence >= self.config.on_road_confidence_min
            and matched.distance_m <= self.config.on_road_distance_max_m
            and sigma <= self.config.max_sigma_for_forced_on_road_m
        )
        if not on_road:
            return MapMatchedPosition(
                timestamp=state.timestamp,
                lat_snapped=state.latitude,
                lon_snapped=state.longitude,
                heading_snapped_rad=state.yaw_rad,
                road_segment_id=matched.road_segment_id,
                confidence_score=confidence,
                is_on_road_network=False,
                distance_to_road_m=matched.distance_m,
            )

        return MapMatchedPosition(
            timestamp=state.timestamp,
            lat_snapped=matched.projected_latitude,
            lon_snapped=matched.projected_longitude,
            heading_snapped_rad=matched.road_heading_rad,
            road_segment_id=matched.road_segment_id,
            confidence_score=confidence,
            is_on_road_network=True,
            distance_to_road_m=matched.distance_m,
        )
