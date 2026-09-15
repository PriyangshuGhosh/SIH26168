from __future__ import annotations

import math

import numpy as np
import pytest

from sih26168_alignment.frame_aligner import FrameAligner
from sih26168_alignment.simulator import generate_scenario
from sih26168_alignment.types import CalibrationStatus, FrameAlignerConfig, OptionalGnssAid


def _run(sc, use_gnss: bool = True) -> list:
    al = FrameAligner(FrameAlignerConfig())
    frames = []
    for i in range(sc.t.size):
        if use_gnss and sc.gnss_speed is not None and np.isfinite(sc.gnss_speed[i]):
            al.feed_gnss(
                OptionalGnssAid(
                    timestamp=float(sc.t[i]),
                    speed_mps=float(sc.gnss_speed[i]),
                    hdop=float(sc.gnss_hdop[i]) if sc.gnss_hdop is not None else 1.2,
                    num_sats=int(sc.gnss_sats[i]) if sc.gnss_sats is not None else 10,
                )
            )
        frames.append(
            al.process(
                float(sc.t[i]),
                float(sc.acc_p[i, 0]),
                float(sc.acc_p[i, 1]),
                float(sc.acc_p[i, 2]),
                float(sc.gyro_p[i, 0]),
                float(sc.gyro_p[i, 1]),
                float(sc.gyro_p[i, 2]),
            )
        )
    return frames


def _max_conf(frames) -> float:
    return max(f.confidence.overall for f in frames)


def _any_status(frames, st) -> bool:
    return any(f.status == st for f in frames)


def test_stationary_does_not_claim_full_yaw():
    sc = generate_scenario("stationary_phone")
    frames = _run(sc, use_gnss=False)
    assert _any_status(frames, CalibrationStatus.ROLL_PITCH_VALID) or _any_status(
        frames, CalibrationStatus.STATIC_DETECTED
    )
    assert not _any_status(frames, CalibrationStatus.FULLY_ALIGNED)
    assert _max_conf(frames) < 0.62


def test_weak_acceleration_does_not_lock_yaw():
    sc = generate_scenario("weak_acceleration")
    frames = _run(sc, use_gnss=False)
    assert not _any_status(frames, CalibrationStatus.FULLY_ALIGNED)
    last = frames[-1]
    assert last.status in {
        CalibrationStatus.ROLL_PITCH_VALID,
        CalibrationStatus.YAW_UNCERTAIN,
        CalibrationStatus.STATIC_DETECTED,
        CalibrationStatus.DEGRADED,
    }


def test_pothole_does_not_create_false_high_confidence_yaw():
    sc = generate_scenario("pothole")
    frames = _run(sc, use_gnss=False)
    shock_i = int(3.4 * 100)
    window = frames[shock_i : shock_i + 8]
    for f in window:
        assert f.status != CalibrationStatus.FULLY_ALIGNED or f.confidence.yaw_observability < 0.95


def test_phone_movement_degrades():
    sc = generate_scenario("phone_movement")
    frames = _run(sc)
    moved = frames[int(3.2 * 100) :]
    statuses = {f.status for f in moved}
    assert CalibrationStatus.REINITIALIZING in statuses or CalibrationStatus.DEGRADED in statuses or (
        CalibrationStatus.UNINITIALIZED in statuses
    ) or CalibrationStatus.ROLL_PITCH_VALID in statuses
    # Must not remain confidently fully aligned through a large remount.
    confident_full = [
        f
        for f in frames[int(3.8 * 100) :]
        if f.status == CalibrationStatus.FULLY_ALIGNED and f.confidence.overall > 0.6
    ]
    assert len(confident_full) == 0


def test_nan_and_inf_invalid():
    al = FrameAligner()
    for i in range(20):
        al.process(0.01 * i, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
    bad = al.process(0.21, math.nan, 0.0, 9.8, 0.0, 0.0, 0.0)
    assert bad.status == CalibrationStatus.INVALID
    assert bad.confidence.overall <= 0.05
    inf = al.process(0.22, 0.0, 0.0, math.inf, 0.0, 0.0, 0.0)
    assert inf.status == CalibrationStatus.INVALID


def test_timestamp_regression():
    al = FrameAligner()
    al.process(1.0, 0, 0, 9.8, 0, 0, 0)
    bad = al.process(0.5, 0, 0, 9.8, 0, 0, 0)
    assert bad.status == CalibrationStatus.INVALID


def test_gnss_assisted_can_align():
    sc = generate_scenario("gnss_assisted")
    frames = _run(sc, use_gnss=True)
    last = frames[-1]
    assert last.status == CalibrationStatus.FULLY_ALIGNED
    a_v = last.accel_v()
    assert abs(a_v[2] - 9.80665) < 1.5


def test_straight_accel_maps_gravity_to_z():
    sc = generate_scenario("straight_acceleration")
    frames = _run(sc, use_gnss=True)
    last = frames[-1]
    assert last.status in {
        CalibrationStatus.FULLY_ALIGNED,
        CalibrationStatus.YAW_UNCERTAIN,
        CalibrationStatus.ROLL_PITCH_VALID,
        CalibrationStatus.DEGRADED,
    }
    if last.status == CalibrationStatus.FULLY_ALIGNED:
        R_err = []
        # Compare aligned accel to vehicle truth near end (mostly gravity)
        i = -5
        f = frames[i]
        assert abs(f.az_v - sc.acc_v[i, 2]) < 1.0
        assert abs(f.ax_v - sc.acc_v[i, 0]) < 1.2


def test_vibration_does_not_explode_quaternion():
    sc = generate_scenario("vibration")
    frames = _run(sc, use_gnss=False)
    for f in frames:
        assert abs(np.linalg.norm(f.q_pv) - 1.0) < 1e-6
        assert np.all(np.isfinite(f.q_pv))
        assert np.isfinite(f.ax_v)
