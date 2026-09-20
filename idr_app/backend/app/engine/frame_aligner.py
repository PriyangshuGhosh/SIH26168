from __future__ import annotations

import math

import numpy as np

from .types import AlignedImu, CalibrationStatus, ImuSample


def _quat_from_rotmat(R: np.ndarray) -> tuple[float, float, float, float]:
    tr = float(np.trace(R))
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    else:
        i = int(np.argmax([R[0, 0], R[1, 1], R[2, 2]]))
        if i == 0:
            s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
            w = (R[2, 1] - R[1, 2]) / s
            x = 0.25 * s
            y = (R[0, 1] + R[1, 0]) / s
            z = (R[0, 2] + R[2, 0]) / s
        elif i == 1:
            s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
            w = (R[0, 2] - R[2, 0]) / s
            x = (R[0, 1] + R[1, 0]) / s
            y = 0.25 * s
            z = (R[1, 2] + R[2, 1]) / s
        else:
            s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
            w = (R[1, 0] - R[0, 1]) / s
            x = (R[0, 2] + R[2, 0]) / s
            y = (R[1, 2] + R[2, 1]) / s
            z = 0.25 * s
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    return (w / n, x / n, y / n, z / n)


def rot_phone_to_vehicle(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


class FrameAligner:
    """Phone IMU → vehicle frame (+X forward, +Y left, +Z up)."""

    def __init__(self) -> None:
        self._g_est = np.array([0.0, 0.0, 9.81])
        self._fwd_est = np.array([1.0, 0.0, 0.0])
        self._static_n = 0
        self._motion_n = 0
        self._R = np.eye(3)
        self._status = CalibrationStatus.UNKNOWN
        self._conf = 0.0
        self._q = (1.0, 0.0, 0.0, 0.0)
        self._lp = np.zeros(3)
        self._have_static = False
        self._have_yaw = False

    def reset(self) -> None:
        self.__init__()

    def feed(self, sample: ImuSample) -> AlignedImu:
        a = np.array([sample.ax, sample.ay, sample.az], dtype=float)
        w = np.array([sample.gx, sample.gy, sample.gz], dtype=float)
        self._lp = 0.95 * self._lp + 0.05 * a
        gyro_n = float(np.linalg.norm(w))
        acc_n = float(np.linalg.norm(a))
        static = abs(acc_n - 9.81) < 0.6 and gyro_n < 0.12
        if static:
            self._static_n += 1
            self._g_est = 0.98 * self._g_est + 0.02 * a
            if self._static_n > 40:
                self._have_static = True
                self._status = CalibrationStatus.STATIC_OK
        else:
            self._static_n = max(0, self._static_n - 1)

        if self._have_static and gyro_n < 0.35:
            a_h = a - self._g_est * (np.dot(a, self._g_est) / (np.dot(self._g_est, self._g_est) + 1e-9))
            if float(np.linalg.norm(a_h)) > 0.8:
                self._fwd_est = 0.9 * self._fwd_est + 0.1 * a_h
                self._motion_n += 1
                if self._motion_n > 30:
                    self._have_yaw = True

        if self._have_static:
            z = self._g_est / (np.linalg.norm(self._g_est) + 1e-9)
            f = self._fwd_est - z * np.dot(self._fwd_est, z)
            fn = np.linalg.norm(f)
            if fn < 1e-6:
                f = np.array([1.0, 0.0, 0.0]) - z * z[0]
                fn = np.linalg.norm(f) + 1e-9
            x = f / fn
            y = np.cross(z, x)
            yn = np.linalg.norm(y) + 1e-9
            y = y / yn
            x = np.cross(y, z)
            x = x / (np.linalg.norm(x) + 1e-9)
            # Rows of R map phone vectors into vehicle: x=fwd, y=left, z=up
            self._R = np.vstack([x, y, z])
            self._q = _quat_from_rotmat(self._R)
            if self._have_yaw:
                self._status = CalibrationStatus.ALIGNED
                self._conf = min(1.0, 0.55 + 0.01 * self._motion_n)
            else:
                self._status = CalibrationStatus.YAW_PENDING
                self._conf = 0.35
        else:
            self._status = CalibrationStatus.UNKNOWN
            self._conf = 0.05

        av = self._R @ a
        wv = self._R @ w
        return AlignedImu(
            timestamp=sample.timestamp,
            ax_v=float(av[0]),
            ay_v=float(av[1]),
            az_v=float(av[2]),
            gx_v=float(wv[0]),
            gy_v=float(wv[1]),
            gz_v=float(wv[2]),
            q_pv=self._q,
            status=self._status,
            confidence=self._conf,
        )
