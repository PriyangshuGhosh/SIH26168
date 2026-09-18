"""Hostile yaw / false high-confidence regression tests."""

from __future__ import annotations

import math

import numpy as np

from sih26168_alignment.frame_aligner import FrameAligner
from sih26168_alignment.frames import (
    orthonormal_error,
    rotation_det,
    rotation_matrix_from_quat,
    rotation_zyx,
    vehicleToPhoneVector,
)
from sih26168_alignment.types import CalibrationStatus, FrameAlignerConfig, OptionalGnssAid

G = 9.80665
DT = 0.01
FULL = CalibrationStatus.FULLY_ALIGNED
MOUNT = rotation_zyx(-1.4, 0.35, -0.8)


def _yaw_error_rad(R_est: np.ndarray, R_true: np.ndarray) -> float:
    x = R_true.T @ R_est @ np.array([1.0, 0.0, 0.0])
    h = x[:2]
    n = float(np.linalg.norm(h))
    if n < 1e-9:
        return math.pi
    return abs(math.atan2(h[1] / n, h[0] / n))


def _drive(acc_v, gyro_v, R_vp, gnss_speed=None, feed_gnss=True, cfg=None):
    al = FrameAligner(cfg or FrameAlignerConfig())
    frames = []
    for i in range(acc_v.shape[0]):
        t = i * DT
        ap = vehicleToPhoneVector(R_vp, acc_v[i])
        gp = vehicleToPhoneVector(R_vp, gyro_v[i])
        if feed_gnss and gnss_speed is not None:
            al.feed_gnss(
                OptionalGnssAid(
                    timestamp=t,
                    speed_mps=float(gnss_speed[i]),
                    hdop=1.2,
                    num_sats=10,
                )
            )
        frames.append(
            al.process(t, float(ap[0]), float(ap[1]), float(ap[2]), float(gp[0]), float(gp[1]), float(gp[2]))
        )
    return al, frames


def _static_then(n_static: int, n_rest: int, fill, ax0=0.0):
    n = n_static + n_rest
    acc = np.zeros((n, 3))
    gyro = np.zeros((n, 3))
    acc[:, 2] = G
    acc[:, 0] = ax0
    fill(acc, gyro, n_static)
    return acc, gyro


def _speed_from_ax(acc):
    v = 0.0
    s = np.zeros(acc.shape[0])
    for i in range(acc.shape[0]):
        v = max(0.0, v + acc[i, 0] * DT)
        s[i] = v
    return s


def _false_high_conf(frames, R_true, min_err_deg=45.0, min_overall=0.45) -> int:
    n = 0
    for f in frames:
        if f.status != FULL:
            continue
        R = rotation_matrix_from_quat(f.q_pv)
        if _yaw_error_rad(R, R_true) > math.radians(min_err_deg) and f.confidence.overall >= min_overall:
            n += 1
    return n


def test_lane_change_plus_gnss_must_not_false_lock():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 250):
            acc[i, 1] = 2.0
            acc[i, 0] = 0.2
            gyro[i, 2] = 0.05

    acc, gyro = _static_then(80, 400, fill)
    speed = np.linspace(5.0, 12.0, acc.shape[0])
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    assert _false_high_conf(frames, MOUNT) == 0
    assert not any(f.status == FULL and f.confidence.overall >= 0.62 for f in frames)


def test_lateral_dominant_with_gnss_ramp_not_fully_aligned():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 300):
            acc[i, 1] = 2.2
            acc[i, 0] = 0.15
            gyro[i, 2] = 0.03

    acc, gyro = _static_then(80, 350, fill)
    speed = np.linspace(8.0, 16.0, acc.shape[0])
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    assert _false_high_conf(frames, MOUNT) == 0
    assert not any(f.status == FULL for f in frames)


def test_stationary_roll_pitch_not_full():
    acc, gyro = _static_then(300, 0, lambda *_: None)
    _, frames = _drive(acc, gyro, MOUNT, feed_gnss=False)
    assert any(f.status == CalibrationStatus.ROLL_PITCH_VALID for f in frames)
    assert not any(f.status == FULL for f in frames)
    assert max(f.confidence.overall for f in frames) < 0.62


def test_constant_speed_straight_yaw_uncertain_or_tilt_only():
    acc, gyro = _static_then(80, 400, lambda *_: None)
    speed = np.full(acc.shape[0], 20.0)
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    assert not any(f.status == FULL for f in frames)


def test_constant_speed_curve_does_not_invent_yaw():
    def fill(acc, gyro, s0):
        for i in range(s0, acc.shape[0]):
            gyro[i, 2] = 0.35
            acc[i, 1] = 0.35 * 15.0

    acc, gyro = _static_then(80, 400, fill)
    speed = np.full(acc.shape[0], 15.0)
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    assert not any(f.status == FULL for f in frames)


def test_quantized_gnss_does_not_force_yaw():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 250):
            acc[i, 0] = 0.08

    acc, gyro = _static_then(80, 300, fill)
    true = 10.0 + 0.05 * np.arange(acc.shape[0]) * DT
    q = np.round(true / (1.0 / 3.6)) * (1.0 / 3.6)
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=q)
    assert not any(f.status == FULL for f in frames)


def test_noisy_gnss_does_not_force_yaw():
    rng = np.random.default_rng(26168)

    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 250):
            acc[i, 0] = 0.12

    acc, gyro = _static_then(80, 300, fill)
    speed = np.maximum(8.0 + rng.normal(0.0, 1.5, size=acc.shape[0]), 0.0)
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    assert _false_high_conf(frames, MOUNT) == 0
    assert not any(f.status == FULL for f in frames)


def test_stale_gnss_does_not_sign_yaw():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 250):
            acc[i, 0] = 2.2

    acc, gyro = _static_then(80, 300, fill)
    al = FrameAligner()
    al.feed_gnss(OptionalGnssAid(timestamp=0.0, speed_mps=12.0, hdop=1.0, num_sats=10))
    frames = []
    for i in range(acc.shape[0]):
        t = i * DT
        ap = vehicleToPhoneVector(MOUNT, acc[i])
        gp = vehicleToPhoneVector(MOUNT, gyro[i])
        frames.append(al.process(t, *map(float, ap), *map(float, gp)))
    # Without fresh GNSS, sign must not lock from a single stale aid.
    assert not any(f.status == FULL for f in frames)


def test_gnss_spike_ignored():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 200):
            acc[i, 0] = 2.2

    acc, gyro = _static_then(80, 250, fill)
    speed = _speed_from_ax(acc)
    speed[120] = speed[119] + 25.0
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    # Spike must not be required for correctness; must not create a 180° lock by itself.
    # Honest accel+GNSS after the spike may still align — only forbid huge yaw error.
    assert _false_high_conf(frames, MOUNT, min_err_deg=90.0) == 0


def test_mild_accel_does_not_poison_gravity():
    def fill(acc, gyro, s0):
        for i in range(s0, acc.shape[0]):
            acc[i, 0] = 1.5

    acc, gyro = _static_then(100, 200, fill)
    al, frames = _drive(acc, gyro, MOUNT, feed_gnss=False)
    g_true = MOUNT.T @ np.array([0.0, 0.0, 1.0])
    g_est = al._g_up_p
    ang = float(np.arccos(np.clip(np.dot(g_est, g_true), -1.0, 1.0)))
    assert ang < math.radians(3.0)
    # 1.5 m/s² is observable horizontally (not absorbed into gravity).
    i = 150
    f = frames[i]
    R = rotation_matrix_from_quat(f.q_pv)
    a_level = R @ vehicleToPhoneVector(MOUNT, acc[i])
    assert abs(a_level[2] - G) < 0.35


def test_honest_forward_accel_can_lock():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 300):
            acc[i, 0] = 2.2

    acc, gyro = _static_then(120, 350, fill)
    speed = _speed_from_ax(acc)
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    last = frames[-1]
    assert last.status == FULL
    assert last.confidence.overall >= 0.62
    err = math.degrees(_yaw_error_rad(rotation_matrix_from_quat(last.q_pv), MOUNT))
    assert err < 8.0


def test_accel_then_turn_without_gnss_can_lock():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 220):
            acc[i, 0] = 2.2
        v = 2.2 * 2.2
        for i in range(s0 + 240, s0 + 420):
            gyro[i, 2] = 0.45
            acc[i, 1] = 0.45 * max(v, 4.0)

    acc, gyro = _static_then(120, 450, fill)
    _, frames = _drive(acc, gyro, MOUNT, feed_gnss=False)
    full = [f for f in frames if f.status == FULL]
    assert len(full) > 0
    last_full = full[-1]
    assert last_full.confidence.overall >= 0.62
    err = math.degrees(_yaw_error_rad(rotation_matrix_from_quat(last_full.q_pv), MOUNT))
    assert err < 12.0


def test_fully_aligned_requires_documented_overall_floor():
    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 300):
            acc[i, 0] = 2.2

    acc, gyro = _static_then(120, 350, fill)
    speed = _speed_from_ax(acc)
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    for f in frames:
        if f.status == FULL:
            assert f.confidence.overall >= 0.62 - 1e-9


def test_potholes_and_vibration_no_false_full():
    rng = np.random.default_rng(7)

    def fill(acc, gyro, s0):
        acc[s0:] += rng.normal(0.0, 0.25, size=acc[s0:].shape)
        gyro[s0:] += rng.normal(0.0, 0.04, size=gyro[s0:].shape)
        for k in range(10):
            i = s0 + 30 * k
            acc[i : i + 3, 2] += np.array([11.0, -7.0, 3.0])

    acc, gyro = _static_then(80, 400, fill)
    speed = np.linspace(6.0, 9.0, acc.shape[0])
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    assert _false_high_conf(frames, MOUNT) == 0


def test_reverse_unsigned_gnss_is_180_ambiguous_not_lateral():
    """Unsigned GNSS speed while reversing is indistinguishable from forward accel.

    A 180° lock is a documented limitation. A ~90° lock would mean we treated
    reverse as a lateral axis and is not acceptable.
    """

    def fill(acc, gyro, s0):
        for i in range(s0, s0 + 200):
            acc[i, 0] = -2.2
        for i in range(s0 + 220, s0 + 380):
            gyro[i, 2] = 0.4
            acc[i, 1] = 0.4 * (-8.0)

    acc, gyro = _static_then(100, 400, fill)
    v = 0.0
    speed = np.zeros(acc.shape[0])
    for i in range(acc.shape[0]):
        v = v + acc[i, 0] * DT
        speed[i] = abs(v)
    _, frames = _drive(acc, gyro, MOUNT, gnss_speed=speed)
    for f in frames:
        if f.status == FULL and f.confidence.overall >= 0.62:
            e = math.degrees(_yaw_error_rad(rotation_matrix_from_quat(f.q_pv), MOUNT))
            wrap = min(e, abs(180.0 - e))
            assert wrap < 40.0, f"reverse produced non-sign yaw error {e:.1f} deg"


def test_numerical_stability_no_nan_on_adversarial():
    def fill(acc, gyro, s0):
        for i in range(s0, acc.shape[0]):
            acc[i, 0] = 2.0 * math.sin(0.2 * i)
            acc[i, 1] = 1.2 * math.cos(0.13 * i)
            gyro[i, 2] = 0.4 * math.sin(0.05 * i)

    acc, gyro = _static_then(80, 400, fill)
    _, frames = _drive(acc, gyro, MOUNT, feed_gnss=False)
    for f in frames:
        assert np.all(np.isfinite(f.q_pv))
        assert abs(np.linalg.norm(f.q_pv) - 1.0) < 1e-6
        R = rotation_matrix_from_quat(f.q_pv)
        assert orthonormal_error(R) < 1e-6
        assert abs(rotation_det(R) - 1.0) < 1e-6
        assert np.isfinite(f.ax_v) and np.isfinite(f.confidence.overall)
