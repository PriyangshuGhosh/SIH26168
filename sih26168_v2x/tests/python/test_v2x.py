from __future__ import annotations

import math

from sih26168_v2x.core import V2XCore
from sih26168_v2x.frames import (
    geo_to_local_enu,
    heading_speed_to_enu,
    local_enu_to_geo,
    vehicle_frame_to_navigation_enu,
)
from sih26168_v2x.security import MockSecurityProvider
from sih26168_v2x.simulator import V2XSimulator, parse_jsonl_line, scenario
from sih26168_v2x.timestamp import age_inflation_scale, evaluate_timing
from sih26168_v2x.types import (
    CHI2_DOF2_P95,
    EnuOrigin,
    GeoPosition,
    LocalNavigationState,
    NormalizedV2XMessage,
    SecurityStatus,
    TimestampPair,
    V2XConfig,
    GateDecision,
)
from sih26168_v2x.cooperative import should_use_measurement, CooperativeMeasurement


ORIGIN = EnuOrigin(12.9716, 77.5946, 920.0, True)


def _cam(vid, t, lat, lon, ve=0.0, vn=15.0):
    m = NormalizedV2XMessage()
    m.vehicle_id = vid
    m.time = TimestampPair(t, t + 0.05, 0.0, 0.0)
    m.geo = GeoPosition(lat, lon, 920.0)
    m.velocity_enu.east_m = ve
    m.velocity_enu.north_m = vn
    m.declared_pos_std_m = 3.0
    return m


def _local(t, lat, lon, gnss):
    s = LocalNavigationState()
    s.timestamp_s = t
    s.latitude_deg = lat
    s.longitude_deg = lon
    s.altitude_m = 920.0
    s.v_x = 15.0
    s.valid = True
    s.gnss_available = gnss
    return s


def test_geo_roundtrip():
    g = GeoPosition(12.9726, 77.5956, 925.0)
    enu = geo_to_local_enu(g, ORIGIN)
    assert 100 < enu.north_m < 120
    back = local_enu_to_geo(enu, ORIGIN)
    assert abs(back.latitude_deg - g.latitude_deg) < 1e-9
    assert abs(back.longitude_deg - g.longitude_deg) < 1e-9


def test_member3_yaw_zero_is_north():
    ve, vn = vehicle_frame_to_navigation_enu(10.0, 0.0, 0.0)
    assert abs(vn - 10.0) < 1e-12 and abs(ve) < 1e-12
    ve, vn = vehicle_frame_to_navigation_enu(10.0, 0.0, math.pi / 2)
    assert abs(ve - 10.0) < 1e-12 and abs(vn) < 1e-12
    ve, vn = heading_speed_to_enu(0.0, 20.0)
    assert abs(vn - 20) < 1e-12


def test_age_and_stale():
    t = evaluate_timing(TimestampPair(1.0, 1.4, 0.0, 0.0), 0.5, 1.5, 1e-4)
    assert abs(t.message_age_s - 0.4) < 1e-12
    t = evaluate_timing(TimestampPair(1.0, 4.0, 0.0, 0.0), 0.5, 1.5, 1e-4)
    assert t.stale
    assert age_inflation_scale(0.2, 0.2) > 1.3


def test_rejects_nan_inf_untrusted_duplicate():
    core = V2XCore(V2XConfig(origin_locked=True))
    core.lock_origin(ORIGIN)
    bad = _cam("r", 1.0, float("nan"), 77.59)
    core.ingest(bad)
    bad = _cam("r", 1.0, 12.97, 77.59)
    bad.velocity_enu.north_m = float("inf")
    core.ingest(bad)
    bad = _cam("r", 1.0, 12.97, 77.59)
    bad.declared_security = SecurityStatus.UNTRUSTED
    core.ingest(bad)
    assert not core.tracks
    core.ingest(_cam("r", 2.0, 12.9717, 77.5946))
    core.ingest(_cam("r", 2.0, 12.9717, 77.5946))
    assert core.health.duplicates >= 1


def test_no_v2x_and_gnss_correlation():
    core = V2XCore(V2XConfig(origin_locked=True))
    core.lock_origin(ORIGIN)
    r = core.get_cooperative_measurement(_local(1.0, 12.9716, 77.5946, False))
    assert r.decision == GateDecision.UNAVAILABLE
    core.ingest(_cam("lead", 1.0, 12.9718, 77.5946))
    r = core.get_cooperative_measurement(_local(1.0, 12.9716, 77.5946, True))
    assert r.reason == "correlated_with_gnss"
    r = core.get_cooperative_measurement(_local(2.0, 12.9716, 77.5946, False))
    assert r.measurement and r.measurement.has_position


def test_gating_thresholds():
    cfg = V2XConfig()
    local = _local(1.0, ORIGIN.latitude_deg, ORIGIN.longitude_deg, False)
    meas = CooperativeMeasurement(has_position=True, north_m=0.0, east_m=0.0,
                                  position_cov_ne=[[4.0, 0.0], [0.0, 4.0]])
    d, nis, _ = should_use_measurement(local, ORIGIN, meas, cfg)
    assert d == GateDecision.ACCEPT
    meas.north_m = 200.0
    d, nis, _ = should_use_measurement(local, ORIGIN, meas, cfg)
    assert d == GateDecision.REJECT
    assert CHI2_DOF2_P95 == 5.991


def test_simulator_determinism_and_replay(tmp_path):
    a = V2XSimulator(scenario("convoy", seed=9))
    b = V2XSimulator(scenario("convoy", seed=9))
    ma, mb = a.messages_at(1.0), b.messages_at(1.0)
    assert len(ma) == len(mb)
    if ma:
        assert ma[0].geo.latitude_deg == mb[0].geo.latitude_deg
    path = tmp_path / "log.jsonl"
    V2XSimulator(scenario("sparse", seed=2)).write_jsonl(str(path), 0.3)
    lines = path.read_text().strip().splitlines()
    assert parse_jsonl_line(lines[0]) is not None
    assert parse_jsonl_line("{not json") is None


def test_mock_security_never_authenticates():
    cfg = V2XConfig()
    m = _cam("x", 1.0, 12.97, 77.59)
    m.declared_security = SecurityStatus.AUTHENTICATED
    st, _ = MockSecurityProvider().evaluate(m, cfg)
    assert st == SecurityStatus.UNVERIFIED


def test_malformed_does_not_crash():
    core = V2XCore()
    m = NormalizedV2XMessage()
    core.ingest(m)
    assert core.health.rejected >= 1


def test_experiment_smoke():
    from sih26168_v2x.experiments import run_blackout
    m0 = run_blackout(0, "imu", seed=1, dt=1.0)
    m1 = run_blackout(1, "v2x_gated", seed=1, dt=1.0)
    assert m0.n > 10 and m1.n > 10
