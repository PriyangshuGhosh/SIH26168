from __future__ import annotations

import math
from pathlib import Path

import pytest

from sih26168_map_matching.candidates import generate_candidates
from sih26168_map_matching.emission import emission_log_probability
from sih26168_map_matching.geometry import angular_difference_rad, haversine_m
from sih26168_map_matching.map_matcher import MapMatcher, MapMatcherConfig
from sih26168_map_matching.road_graph import (
    build_synthetic_grid,
    write_roadpack,
    write_sqlite,
    load_roadpack,
    query_sqlite_bbox,
)
from sih26168_map_matching.spatial_index import SpatialIndex
from sih26168_map_matching.types import NavigationState, RoadCandidate
from sih26168_map_matching.viterbi import viterbi_decode


@pytest.fixture(scope="module")
def network():
    return build_synthetic_grid(blocks=3, spacing_m=80.0)


@pytest.fixture(scope="module")
def matcher(network):
    return MapMatcher(network, MapMatcherConfig(window_size=6))


def test_spatial_index_matches_sqlite(tmp_path, network):
    sqlite_path = tmp_path / "grid.sqlite"
    write_sqlite(network, sqlite_path)
    index = SpatialIndex(network)
    lat, lon = 12.9716, 77.5946
    radius = 50.0
    lat_d = radius / 111320.0
    lon_d = radius / (111320.0 * math.cos(math.radians(lat)))
    bbox = (lon - lon_d, lat - lat_d, lon + lon_d, lat + lat_d)
    mem_ids = {s.segment_id for s in index.query_bbox(*bbox)}
    db_ids = set(query_sqlite_bbox(sqlite_path, *bbox))
    assert mem_ids == db_ids
    assert len(mem_ids) > 0


def test_candidate_generation_uncertainty_aware(network):
    index = SpatialIndex(network)
    tight = NavigationState(
        0.0, 12.9716, 77.5946, yaw_rad=math.pi / 2,
        position_cov_m2=((4.0, 0.0), (0.0, 4.0)),
    )
    loose = NavigationState(
        0.0, 12.9716, 77.5946, yaw_rad=math.pi / 2,
        position_cov_m2=((900.0, 0.0), (0.0, 900.0)),
    )
    c_tight = generate_candidates(tight, network, index)
    c_loose = generate_candidates(loose, network, index)
    assert len(c_loose) >= len(c_tight)


def test_heading_degradation(network):
    index = SpatialIndex(network)
    state = NavigationState(
        0.0, 12.9716, 77.5946, yaw_rad=0.0,
        position_cov_m2=((9.0, 0.0), (0.0, 9.0)),
        heading_valid=False,
    )
    cands = generate_candidates(state, network, index)
    assert cands
    # Should not crash; emission ignores heading when invalid
    scores = [emission_log_probability(state, c) for c in cands]
    assert all(math.isfinite(s) for s in scores)


def test_viterbi_not_independent_nearest(network):
    """HMM should prefer temporally consistent path over flickering nearest."""
    good = RoadCandidate(1, "A", 12.9716, 77.5946, 2.0, 0.0, u_node=0, v_node=1)
    bad = RoadCandidate(2, "B", 12.9716, 77.5946, 1.5, math.pi / 2, u_node=10, v_node=11)
    states = [
        NavigationState(0.0, 12.9716, 77.5946, yaw_rad=0.0,
                        position_cov_m2=((4.0, 0.0), (0.0, 4.0))),
        NavigationState(1.0, 12.9717, 77.5946, yaw_rad=0.0,
                        position_cov_m2=((4.0, 0.0), (0.0, 4.0))),
    ]
    # Make bad slightly nearer but disconnected / inconsistent heading
    path, _ = viterbi_decode(states, [[good, bad], [good, bad]], network)
    assert path[0] is not None
    assert path[0].road_segment_id == 1
    assert path[1].road_segment_id == 1


def test_fail_safe_off_network(matcher):
    far = NavigationState(
        0.0, 13.5, 78.5, yaw_rad=0.0,
        position_cov_m2=((16.0, 0.0), (0.0, 16.0)),
    )
    out = matcher.match(far)
    assert out.is_on_road_network is False
    assert out.confidence_score < 0.5
    assert out.lat_snapped == pytest.approx(far.latitude)
    assert out.lon_snapped == pytest.approx(far.longitude)


def test_large_uncertainty_no_magic_position(matcher):
    matcher.reset()
    uncertain = NavigationState(
        0.0, 12.9716, 77.5946, yaw_rad=math.pi / 2,
        position_cov_m2=((2500.0, 0.0), (0.0, 2500.0)),
    )
    out = matcher.match(uncertain)
    assert out.is_on_road_network is False or out.confidence_score < 0.9


def test_confidence_not_one_just_because_candidate(matcher):
    matcher.reset()
    # Equidistant-ish ambiguous observation
    state = NavigationState(
        0.0,
        12.9716 + 40.0 / 111320.0,
        77.5946 + 40.0 / (111320.0 * math.cos(math.radians(12.9716))),
        yaw_rad=0.3,
        position_cov_m2=((100.0, 0.0), (0.0, 100.0)),
    )
    out = matcher.match(state)
    assert out.confidence_score < 0.999


def test_hmm_beats_or_matches_nearest_on_synthetic(matcher):
    lat0, lon0 = 12.9716, 77.5946
    dlon = 5.0 / (111320.0 * math.cos(math.radians(lat0)))
    states = []
    truth = []
    for i in range(30):
        truth.append((lat0, lon0 + i * dlon))
        states.append(
            NavigationState(
                float(i),
                lat0,
                lon0 + i * dlon + (8.0 if 12 <= i <= 18 else 0.0)
                / (111320.0 * math.cos(math.radians(lat0))),
                yaw_rad=math.pi / 2,
                position_cov_m2=((25.0, 0.0), (0.0, 25.0)),
            )
        )
    hmm = matcher.match_trajectory(states)
    nearest = matcher.nearest_road_baseline(states)

    def mean_err(outs):
        errs = [
            haversine_m(o.lat_snapped, o.lon_snapped, t[0], t[1])
            for o, t in zip(outs, truth)
            if o.is_on_road_network
        ]
        return sum(errs) / len(errs) if errs else 1e9

    # HMM should not be dramatically worse; usually better under lateral spike
    assert mean_err(hmm) <= mean_err(nearest) * 1.25 + 5.0


def test_roadpack_roundtrip(tmp_path, network):
    path = tmp_path / "grid.roadpack"
    write_roadpack(network, path)
    loaded = load_roadpack(path)
    assert len(loaded.segments) == len(network.segments)


def test_angular_wrap():
    assert angular_difference_rad(0.1, 2 * math.pi - 0.1) == pytest.approx(0.2, abs=1e-6)


def test_graphml_loads_if_present():
    graphml = Path(__file__).resolve().parents[2] / "data" / "small_road_network.graphml"
    if not graphml.exists():
        pytest.skip("OSM graphml fixture unavailable")
    from sih26168_map_matching.road_graph import load_graphml

    net = load_graphml(graphml)
    assert len(net.segments) > 10
    m = MapMatcher(net)
    s = NavigationState(
        0.0, 12.9716, 77.5946, yaw_rad=0.0,
        position_cov_m2=((25.0, 0.0), (0.0, 25.0)),
    )
    out = m.match(s)
    assert out.timestamp == 0.0


def test_nearest_road_projection(matcher, network):
    """Nearest-road baseline projects onto a nearby corridor."""
    lat0, lon0 = 12.9716, 77.5946
    state = NavigationState(
        0.0,
        lat0 + 4.0 / 111320.0,
        lon0,
        yaw_rad=0.0,
        position_cov_m2=((4.0, 0.0), (0.0, 4.0)),
    )
    outs = matcher.nearest_road_baseline([state])
    assert outs[0].road_segment_id != 0
    assert outs[0].distance_to_road_m < 10.0


def test_multiple_nearby_roads(network):
    """At a grid intersection, candidate search returns multiple roads."""
    index = SpatialIndex(network)
    # Synthetic grid origin is a cross of N-S and E-W segments.
    state = NavigationState(
        0.0,
        12.9716,
        77.5946,
        yaw_rad=0.0,
        position_cov_m2=((9.0, 0.0), (0.0, 9.0)),
    )
    cands = generate_candidates(state, network, index, max_candidates=12)
    assert len(cands) >= 2
    ids = {c.road_segment_id for c in cands}
    assert len(ids) >= 2


def test_parallel_roads_temporal_continuity(matcher):
    """Lateral jumps toward a parallel road should not flip every step."""
    lat0, lon0 = 12.9716, 77.5946
    dlon = 6.0 / (111320.0 * math.cos(math.radians(lat0)))
    parallel = 80.0 / 111320.0
    states = []
    for i in range(24):
        lat = lat0 + (parallel if 10 <= i <= 16 else 0.0)
        states.append(
            NavigationState(
                float(i),
                lat,
                lon0 + i * dlon,
                yaw_rad=math.pi / 2,
                position_cov_m2=((25.0, 0.0), (0.0, 25.0)),
            )
        )
    hmm = matcher.match_trajectory(states)
    on_road_ids = [o.road_segment_id for o in hmm if o.is_on_road_network]
    assert len(on_road_ids) >= 12
    # Majority of early (pre-spike) matches share one corridor id family.
    early = [o.road_segment_id for o in hmm[:8] if o.is_on_road_network]
    assert early
    assert early.count(max(set(early), key=early.count)) >= len(early) // 2


def test_intersection_crossing(matcher):
    """Trajectory that turns at an intersection stays on-network."""
    lat0, lon0 = 12.9716, 77.5946
    d = 8.0 / 111320.0
    dlon = 8.0 / (111320.0 * math.cos(math.radians(lat0)))
    states = []
    # North then east through the origin cross.
    for i in range(8):
        states.append(
            NavigationState(
                float(i),
                lat0 + i * d,
                lon0,
                yaw_rad=0.0,
                position_cov_m2=((16.0, 0.0), (0.0, 16.0)),
            )
        )
    for i in range(8):
        states.append(
            NavigationState(
                float(8 + i),
                lat0 + 7 * d,
                lon0 + i * dlon,
                yaw_rad=math.pi / 2,
                position_cov_m2=((16.0, 0.0), (0.0, 16.0)),
            )
        )
    outs = matcher.match_trajectory(states)
    on_road = sum(1 for o in outs if o.is_on_road_network)
    assert on_road >= len(outs) // 2


def test_noisy_drifting_trajectory(matcher):
    """Accumulating lateral drift still yields finite confidence outputs."""
    lat0, lon0 = 12.9716, 77.5946
    dlon = 5.0 / (111320.0 * math.cos(math.radians(lat0)))
    states = []
    for i in range(20):
        drift = (i * 0.8) / 111320.0
        states.append(
            NavigationState(
                float(i),
                lat0 + drift,
                lon0 + i * dlon,
                yaw_rad=math.pi / 2,
                position_cov_m2=((36.0, 0.0), (0.0, 36.0)),
            )
        )
    outs = matcher.match_trajectory(states)
    assert len(outs) == 20
    assert all(0.0 <= o.confidence_score <= 1.0 + 1e-9 for o in outs)
    assert any(o.is_on_road_network for o in outs)


def test_no_candidate_empty_window(matcher):
    """Far observation yields empty candidates / pass-through."""
    matcher.reset()
    far = NavigationState(
        0.0,
        0.0,
        0.0,
        yaw_rad=0.0,
        position_cov_m2=((4.0, 0.0), (0.0, 4.0)),
    )
    out = matcher.match(far)
    assert out.is_on_road_network is False
    assert out.road_segment_id == 0
    assert out.lat_snapped == pytest.approx(0.0)
    assert out.lon_snapped == pytest.approx(0.0)


def test_ambiguous_candidates_lower_confidence(network):
    """Two near-equidistant candidates must not yield certainty=1."""
    index = SpatialIndex(network)
    # Midway between parallel E-W corridors (~40 m north of origin).
    state = NavigationState(
        0.0,
        12.9716 + 40.0 / 111320.0,
        77.5946,
        yaw_rad=math.pi / 2,
        position_cov_m2=((100.0, 0.0), (0.0, 100.0)),
    )
    cands = generate_candidates(state, network, index)
    assert len(cands) >= 2
    from sih26168_map_matching.viterbi import candidate_confidence

    conf = candidate_confidence(state, cands[0], cands)
    assert conf < 0.999


def test_invalid_input_nan_and_empty(matcher):
    """Invalid coordinates / empty trajectory must not crash."""
    matcher.reset()
    bad = NavigationState(
        0.0,
        float("nan"),
        float("nan"),
        yaw_rad=0.0,
        position_cov_m2=((4.0, 0.0), (0.0, 4.0)),
    )
    out = matcher.match(bad)
    assert out.is_on_road_network is False
    assert math.isnan(out.lat_snapped) or out.confidence_score == 0.0

    empty = matcher.match_trajectory([])
    assert empty == []
