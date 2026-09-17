"""Reference baselines for IMU-only vehicle speed estimation (all outputs in m/s).

A. :class:`ConstantMeanBaseline` - predicts the training-set mean speed.
B. :class:`RidgeFeatureBaseline` - ridge regression on hand-crafted statistics of the
   ``[B, T, 6]`` IMU window (nothing else is ever passed in).
C. :class:`PhysicsIntegrationBaseline` - causal gravity removal + forward-axis estimation +
   leaky integration with zero-velocity updates. This is a deliberately simple *reference*
   for what naive dead reckoning achieves, not a candidate solution.

All predictions are clipped to ``>= 0`` because the target is a speed.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.data.dataset import ImuDataset
from src.data.windowing import SAMPLE_RATE_HZ, break_mask, iter_window_chunks

# --------------------------------------------------------------------------- A. constant


class ConstantMeanBaseline:
    name = "constant_mean"

    def fit(self, y: np.ndarray) -> "ConstantMeanBaseline":
        if y.size == 0 or not np.isfinite(y).all():
            raise ValueError("training targets must be non-empty and finite")
        self.mean_ = float(np.mean(y))
        return self

    def predict(self, n: int) -> np.ndarray:
        return np.full(n, self.mean_, dtype=np.float64)


# --------------------------------------------------------------------------- B. ridge

SIGNAL_NAMES = ("acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z", "acc_norm", "gyr_norm")
STAT_NAMES = ("mean", "std", "min", "max", "rms", "mean_abs_diff")
FEATURE_NAMES = tuple(f"{s}_{k}" for s in SIGNAL_NAMES for k in STAT_NAMES)


def window_features(windows: np.ndarray) -> np.ndarray:
    """``[B, T, 6]`` IMU windows -> ``[B, 48]`` features (see :data:`FEATURE_NAMES`)."""
    if windows.ndim != 3 or windows.shape[-1] != 6:
        raise ValueError(f"expected [B, T, 6], got {windows.shape}")
    w = windows.astype(np.float64, copy=False)
    sig = np.concatenate([w, np.linalg.norm(w[..., 0:3], axis=-1, keepdims=True),
                          np.linalg.norm(w[..., 3:6], axis=-1, keepdims=True)], axis=-1)
    diff = np.abs(np.diff(sig, axis=1)).mean(axis=1) if sig.shape[1] > 1 else np.zeros(sig[:, 0].shape)
    stats = [sig.mean(axis=1), sig.std(axis=1), sig.min(axis=1), sig.max(axis=1),
             np.sqrt((sig ** 2).mean(axis=1)), diff]
    return np.stack(stats, axis=-1).reshape(len(w), -1)


class RidgeFeatureBaseline:
    name = "ridge_features"

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha

    def fit(self, windows: np.ndarray, y: np.ndarray) -> "RidgeFeatureBaseline":
        self.model_ = make_pipeline(StandardScaler(), Ridge(alpha=self.alpha))
        self.model_.fit(window_features(windows), y)
        return self

    def predict(self, windows: np.ndarray) -> np.ndarray:
        return np.clip(self.model_.predict(window_features(windows)), 0.0, None)

    def predict_indexed(self, imu: np.ndarray, ends: np.ndarray, window: int, chunk_size: int = 50_000) -> np.ndarray:
        """Chunked prediction for windows given by end indices (see ``src.data.windowing``)."""
        parts = [self.predict(w) for w in iter_window_chunks(imu, ends, window, chunk_size)]
        return np.concatenate(parts) if parts else np.empty(0)


# --------------------------------------------------------------------------- C. physics


def _ema(x: np.ndarray, tau_s: float, dt: float) -> np.ndarray:
    """Causal first-order low-pass along axis 0, initialised at the first sample."""
    a = 1.0 - np.exp(-dt / tau_s)
    zi = (1.0 - a) * x[0]
    y, _ = lfilter([a], [1.0, -(1.0 - a)], x, axis=0, zi=np.broadcast_to(zi, (1,) + x.shape[1:]).copy())
    return y


def _causal_rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    c1 = np.concatenate([[0.0], np.cumsum(x)])
    c2 = np.concatenate([[0.0], np.cumsum(x * x)])
    i = np.arange(1, len(x) + 1)
    lo = np.maximum(i - n, 0)
    cnt = i - lo
    mean = (c1[i] - c1[lo]) / cnt
    var = (c2[i] - c2[lo]) / cnt - mean ** 2
    return np.sqrt(np.clip(var, 0.0, None))


@dataclass
class _SegmentSignals:
    a_forward: np.ndarray    # (n,) signed acceleration along the estimated forward axis, m/s^2
    acc_norm_std: np.ndarray  # (n,) causal rolling std of |acc|
    gyr_norm_std: np.ndarray  # (n,) causal rolling std of |gyr|


class PhysicsIntegrationBaseline:
    """Causal, per-session stateful dead reckoning from the IMU only.

    Per contiguous segment (state resets at session starts and continuity breaks):
      1. gravity ``g`` = causal EMA of acc (``gravity_tau_s``);
      2. horizontal linear acceleration ``a_h`` = (acc - g) with its component along g removed;
      3. forward axis ``u`` = principal eigenvector of a causal EMA of ``a_h a_h^T``
         (``axis_tau_s``), with sign kept continuous in time;
      4. ``v_t = exp(-dt / leak_tau_s) * v_{t-1} + (a_h . u) dt``, reset to 0 when the causal
         rolling std of |acc| and |gyr| over ``zupt_window_s`` falls below thresholds (ZUPT);
      5. speed = ``|v|`` (the forward-axis sign is unobservable without an external reference).

    Only ``leak_tau_s`` and ``zupt_acc_std`` are selected by grid search on training rows.
    """

    name = "physics_integration"

    def __init__(self, sample_rate_hz: float = SAMPLE_RATE_HZ, gravity_tau_s: float = 5.0, axis_tau_s: float = 30.0,
                 zupt_window_s: float = 1.0, zupt_acc_std: float = 0.1, zupt_gyr_std: float = 0.02,
                 leak_tau_s: float = 30.0):
        self.dt = 1.0 / sample_rate_hz
        self.sample_rate_hz = sample_rate_hz
        self.gravity_tau_s = gravity_tau_s
        self.axis_tau_s = axis_tau_s
        self.zupt_window_s = zupt_window_s
        self.zupt_acc_std = zupt_acc_std
        self.zupt_gyr_std = zupt_gyr_std
        self.leak_tau_s = leak_tau_s

    def _segment_signals(self, imu: np.ndarray) -> _SegmentSignals:
        acc, gyr = imu[:, 0:3].astype(np.float64), imu[:, 3:6].astype(np.float64)
        g = _ema(acc, self.gravity_tau_s, self.dt)
        g_hat = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
        lin = acc - g
        a_h = lin - np.sum(lin * g_hat, axis=1, keepdims=True) * g_hat
        outer = (a_h[:, :, None] * a_h[:, None, :]).reshape(len(a_h), 9)
        cov = _ema(outer, self.axis_tau_s, self.dt).reshape(-1, 3, 3)
        _, vecs = np.linalg.eigh(cov + 1e-12 * np.eye(3))
        u = vecs[:, :, -1]
        flips = np.ones(len(u))
        flips[1:] = np.where(np.sum(u[1:] * u[:-1], axis=1) < 0, -1.0, 1.0)
        u = u * np.cumprod(flips)[:, None]
        n_win = max(1, int(round(self.zupt_window_s * self.sample_rate_hz)))
        return _SegmentSignals(
            a_forward=np.sum(a_h * u, axis=1),
            acc_norm_std=_causal_rolling_std(np.linalg.norm(acc, axis=1), n_win),
            gyr_norm_std=_causal_rolling_std(np.linalg.norm(gyr, axis=1), n_win),
        )

    def _integrate(self, sig: _SegmentSignals, zupt_acc_std: float, leak_tau_s: float) -> np.ndarray:
        decay = float(np.exp(-self.dt / leak_tau_s))
        stationary = (sig.acc_norm_std < zupt_acc_std) & (sig.gyr_norm_std < self.zupt_gyr_std)
        a_dt = (sig.a_forward * self.dt).tolist()
        out = np.empty(len(a_dt))
        v = 0.0
        for i, (inc, still) in enumerate(zip(a_dt, stationary.tolist())):
            v = 0.0 if still else decay * v + inc
            out[i] = v
        return np.abs(out)

    def _segments(self, ds: ImuDataset) -> list[tuple[int, int]]:
        starts = np.flatnonzero(break_mask(ds, self.sample_rate_hz))
        return list(zip(starts.tolist(), np.r_[starts[1:], len(ds)].tolist()))

    def predict_rows(self, ds: ImuDataset) -> np.ndarray:
        """Per-row causal speed estimate ``(N,)`` for every row of ``ds``."""
        out = np.empty(len(ds))
        for s, e in self._segments(ds):
            out[s:e] = self._integrate(self._segment_signals(ds.imu[s:e]), self.zupt_acc_std, self.leak_tau_s)
        return out

    def fit(self, ds: ImuDataset, ends: np.ndarray, zupt_acc_std_grid: list[float],
            leak_tau_s_grid: list[float]) -> "PhysicsIntegrationBaseline":
        """Grid-search ``zupt_acc_std`` x ``leak_tau_s`` by MAE at training prediction points."""
        segments = self._segments(ds)
        signals = [self._segment_signals(ds.imu[s:e]) for s, e in segments]
        y = ds.target[ends].astype(np.float64)
        self.grid_results_ = []
        for acc_std, leak in itertools.product(zupt_acc_std_grid, leak_tau_s_grid):
            pred = np.empty(len(ds))
            for (s, e), sig in zip(segments, signals):
                pred[s:e] = self._integrate(sig, acc_std, leak)
            score = float(np.mean(np.abs(pred[ends] - y)))
            self.grid_results_.append({"zupt_acc_std": acc_std, "leak_tau_s": leak, "train_mae_mps": score})
        best = min(self.grid_results_, key=lambda r: r["train_mae_mps"])
        self.zupt_acc_std, self.leak_tau_s = best["zupt_acc_std"], best["leak_tau_s"]
        return self
