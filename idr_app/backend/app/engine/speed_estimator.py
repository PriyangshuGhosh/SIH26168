from __future__ import annotations

import numpy as np

from .safety import SpeedValidityFilter
from .types import AlignedImu, SpeedEstimate


WINDOW = 200  # 2 s @ 100 Hz
STRIDE = 10   # ~20 Hz


class SpeedEstimator:
    """Compact linear model over 2 s IMU windows. Trained on synthetic kinematics."""

    def __init__(self) -> None:
        self._buf: list[np.ndarray] = []
        self._times: list[float] = []
        self._w: np.ndarray | None = None
        self._filter = SpeedValidityFilter()
        self._last = SpeedEstimate(0.0, 0.0, 1.0, False, "init")
        self._train()

    def reset(self) -> None:
        self._buf.clear()
        self._times.clear()
        self._filter.reset()
        self._last = SpeedEstimate(0.0, 0.0, 1.0, False, "init")

    def _features(self, win: np.ndarray) -> np.ndarray:
        ax, ay, az, gx, gy, gz = win.T
        rms = lambda v: float(np.sqrt(np.mean(v * v)))
        feats = np.array(
            [
                1.0,
                float(np.mean(ax)),
                float(np.std(ax)),
                rms(ax),
                float(np.mean(np.abs(ay))),
                rms(az - 9.81),
                rms(gx),
                rms(gy),
                rms(gz),
                float(np.percentile(np.abs(ax), 90)),
                float(np.mean(np.cumsum(ax) * 0.01)),
            ],
            dtype=float,
        )
        return feats

    def _train(self) -> None:
        rng = np.random.default_rng(7)
        xs, ys = [], []
        for _ in range(400):
            v = float(rng.uniform(0.0, 28.0))
            a_true = float(rng.normal(0.0, 0.6))
            t = np.arange(WINDOW) * 0.01
            ax = a_true + 0.4 * np.sin(2 * np.pi * 12 * t) + rng.normal(0, 0.15, WINDOW)
            ay = rng.normal(0, 0.2, WINDOW)
            az = 9.81 + rng.normal(0, 0.12, WINDOW)
            gx = rng.normal(0, 0.02, WINDOW)
            gy = rng.normal(0, 0.02, WINDOW)
            gz = rng.normal(0, 0.03, WINDOW)
            win = np.stack([ax, ay, az, gx, gy, gz], axis=1)
            xs.append(self._features(win))
            # Label uses kinematics + vibration-robust proxy
            ys.append(v + 0.35 * float(np.mean(np.cumsum(ax) * 0.01)))
        X = np.vstack(xs)
        y = np.array(ys)
        # Ridge
        lam = 0.4
        xtx = X.T @ X + lam * np.eye(X.shape[1])
        self._w = np.linalg.solve(xtx, X.T @ y)

    def feed(self, aligned: AlignedImu) -> SpeedEstimate:
        row = np.array(
            [aligned.ax_v, aligned.ay_v, aligned.az_v, aligned.gx_v, aligned.gy_v, aligned.gz_v]
        )
        self._buf.append(row)
        self._times.append(aligned.timestamp)
        if len(self._buf) > WINDOW:
            self._buf = self._buf[-WINDOW:]
            self._times = self._times[-WINDOW:]
        if len(self._buf) < WINDOW:
            return self._last
        if (len(self._buf) - WINDOW) % STRIDE != 0 and len(self._buf) != WINDOW:
            return self._last
        win = np.vstack(self._buf[-WINDOW:])
        feats = self._features(win)
        pred = float(feats @ self._w)
        pred = max(0.0, pred)
        # Kinematic blend: integrate mean forward accel over window as a prior
        kin = float(np.clip(np.mean(np.cumsum(win[:, 0]) * 0.01) + abs(np.mean(win[:, 0])) * 8.0, 0, 40))
        # Prefer learned output; blend lightly with energy
        energy = float(np.sqrt(np.mean(win[:, 0] ** 2)))
        blended = 0.55 * pred + 0.25 * kin + 0.20 * (energy * 6.0)
        variance = 0.35 + 0.08 * float(np.std(win[:, 0]))
        checked = self._filter.check(aligned.timestamp, blended, variance)
        self._last = checked
        return checked
