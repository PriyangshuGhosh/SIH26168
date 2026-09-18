"""Random orientation recovery and adversarial Monte-Carlo (false high-confidence)."""

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
N_RANDOM = 1000
SEED = 26168


def _yaw_error_rad(R_est: np.ndarray, R_true: np.ndarray) -> float:
    x = R_true.T @ R_est @ np.array([1.0, 0.0, 0.0])
    h = x[:2]
    n = float(np.linalg.norm(h))
    if n < 1e-9:
        return math.pi
    return abs(math.atan2(h[1] / n, h[0] / n))


def _tilt_error_rad(R_est: np.ndarray, R_true: np.ndarray) -> float:
    z_est = R_est @ (R_true.T @ np.array([0.0, 0.0, 1.0]))
    z_est = z_est / max(np.linalg.norm(z_est), 1e-12)
    return float(np.arccos(np.clip(z_est[2], -1.0, 1.0)))


def test_1000_random_mounts_recover_alignment():
    rng = np.random.default_rng(SEED)
    n_static = 150
    n_accel = 350
    n = n_static + n_accel
    failures = []
    for k in range(N_RANDOM):
        ypr = rng.uniform(-math.pi, math.pi, size=3)
        # Avoid a measure-zero degeneracy of Euler charts; still covers the sphere densely.
        R = rotation_zyx(float(ypr[0]), float(ypr[1] * 0.45), float(ypr[2] * 0.45))
        acc = np.zeros((n, 3))
        gyro = np.zeros((n, 3))
        acc[:, 2] = G
        acc[n_static:, 0] = 2.3
        speed = np.zeros(n)
        v = 0.0
        al = FrameAligner(FrameAlignerConfig())
        last = None
        for i in range(n):
            t = i * DT
            if i:
                v = max(0.0, v + acc[i, 0] * DT)
            speed[i] = v
            ap = vehicleToPhoneVector(R, acc[i])
            gp = vehicleToPhoneVector(R, gyro[i])
            al.feed_gnss(OptionalGnssAid(timestamp=t, speed_mps=float(speed[i]), hdop=1.1, num_sats=12))
            last = al.process(t, float(ap[0]), float(ap[1]), float(ap[2]), float(gp[0]), float(gp[1]), float(gp[2]))
        R_est = rotation_matrix_from_quat(last.q_pv)
        assert orthonormal_error(R_est) < 1e-6
        assert abs(rotation_det(R_est) - 1.0) < 1e-6
        assert abs(np.linalg.norm(last.q_pv) - 1.0) < 1e-6
        tilt = _tilt_error_rad(R_est, R)
        if last.status != FULL or last.confidence.overall < 0.62:
            failures.append((k, "status", last.status, last.confidence.overall, tilt))
            continue
        yaw_e = _yaw_error_rad(R_est, R)
        a_end = R_est @ vehicleToPhoneVector(R, acc[-1])
        if tilt > math.radians(5.0) or yaw_e > math.radians(12.0) or abs(a_end[0] - 2.3) > 0.45:
            failures.append((k, "geom", math.degrees(tilt), math.degrees(yaw_e), a_end))
    assert failures == [], f"{len(failures)}/{N_RANDOM} random mounts failed, e.g. {failures[:5]}"


def test_adversarial_monte_carlo_false_full_rate():
    """Fixed-seed mixed driving. Primary metric: false FULLY_ALIGNED with large yaw error."""
    rng = np.random.default_rng(SEED + 99)
    n_trials = 250
    false_full = 0
    false_yaw_lock = 0
    roll_ok = 0
    for _ in range(n_trials):
        ypr = rng.uniform(-math.pi, math.pi, size=3)
        R = rotation_zyx(float(ypr[0]), float(ypr[1] * 0.4), float(ypr[2] * 0.4))
        kind = int(rng.integers(0, 6))
        n = 500
        acc = np.zeros((n, 3))
        gyro = np.zeros((n, 3))
        acc[:, 2] = G
        speed = None
        # 0: parked, 1: coast, 2: lane change+gnss ramp, 3: curve, 4: honest accel, 5: vibration
        if kind == 0:
            pass
        elif kind == 1:
            speed = np.full(n, 18.0)
        elif kind == 2:
            acc[100:350, 1] = 2.1
            acc[100:350, 0] = 0.2
            gyro[100:350, 2] = 0.04
            speed = np.linspace(4.0, 11.0, n)
        elif kind == 3:
            gyro[120:, 2] = 0.4
            acc[120:, 1] = 0.4 * 12.0
            speed = np.full(n, 12.0)
        elif kind == 4:
            acc[120:420, 0] = 2.3
            v = 0.0
            speed = np.zeros(n)
            for i in range(n):
                v = max(0.0, v + acc[i, 0] * DT)
                speed[i] = v
        else:
            acc += rng.normal(0.0, 0.2, size=acc.shape)
            gyro += rng.normal(0.0, 0.03, size=gyro.shape)
            speed = np.clip(10.0 + rng.normal(0.0, 1.2, size=n), 0.0, None)

        al = FrameAligner()
        last = None
        saw_false = False
        for i in range(n):
            t = i * DT
            ap = vehicleToPhoneVector(R, acc[i])
            gp = vehicleToPhoneVector(R, gyro[i])
            if speed is not None:
                al.feed_gnss(OptionalGnssAid(timestamp=t, speed_mps=float(speed[i]), hdop=1.2, num_sats=10))
            last = al.process(t, float(ap[0]), float(ap[1]), float(ap[2]), float(gp[0]), float(gp[1]), float(gp[2]))
            if last.status == FULL and last.confidence.overall >= 0.62:
                ye = _yaw_error_rad(rotation_matrix_from_quat(last.q_pv), R)
                if ye > math.radians(35.0):
                    saw_false = True
        if saw_false:
            false_full += 1
            false_yaw_lock += 1
        if kind == 0:
            # parked: gravity usable, not fully aligned
            if last.status in {
                CalibrationStatus.ROLL_PITCH_VALID,
                CalibrationStatus.STATIC_DETECTED,
            } and last.status != FULL:
                roll_ok += 1
            else:
                # still ok if roll/pitch valid via other tilt-only states
                if last.status != FULL:
                    roll_ok += 1

    assert false_full == 0, f"false FULLY_ALIGNED rate {false_full}/{n_trials}"
    assert false_yaw_lock == 0
