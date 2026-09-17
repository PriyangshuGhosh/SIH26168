"""Controlled input perturbations for evaluating trained-model robustness (Milestone 3).

These are applied to already-windowed, already-validated ``[B, T, 6]`` IMU tensors at EVALUATION
time only -- never during training. Perturbing values does not change which windows are valid
(session/contiguity/finiteness checks already ran during windowing), so perturbed predictions are
still compared against the SAME true targets, via the existing :func:`src.evaluation.evaluate`
helpers -- no new leakage-prone data path is introduced.

The perturbation magnitudes in ``configs/member1.yaml`` (``robustness.*``) are engineering
assumptions for this controlled test, chosen to be physically plausible for a low-cost smartphone
MEMS IMU (sensor noise floor, a fixed calibration offset, slow bias drift, and a small mounting-
angle error) -- they are not measurements from this dataset and are documented as such.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from src.data.augmentation import random_rotation_matrices, rotate_windows

PerturbFn = Callable[[np.ndarray, np.random.Generator], np.ndarray]


def add_noise(windows: np.ndarray, rng: np.random.Generator, acc_std: float, gyr_std: float) -> np.ndarray:
    """IID Gaussian noise added independently at every time step and axis (sensor noise floor, or
    heavier high-frequency noise for a "vibration" scenario, depending on the std passed in)."""
    out = windows.copy()
    out[..., 0:3] += rng.normal(0.0, acc_std, out[..., 0:3].shape).astype(out.dtype)
    out[..., 3:6] += rng.normal(0.0, gyr_std, out[..., 3:6].shape).astype(out.dtype)
    return out


def add_bias(windows: np.ndarray, rng: np.random.Generator, acc_bias_std: float, gyr_bias_std: float) -> np.ndarray:
    """A constant offset per window (same at every time step), simulating an uncalibrated sensor
    bias that does not change over a single 2-4 s window."""
    b = len(windows)
    out = windows.copy()
    out[..., 0:3] += rng.normal(0.0, acc_bias_std, (b, 1, 3)).astype(out.dtype)
    out[..., 3:6] += rng.normal(0.0, gyr_bias_std, (b, 1, 3)).astype(out.dtype)
    return out


def add_drift(windows: np.ndarray, rng: np.random.Generator, acc_drift_per_s: float, gyr_drift_per_s: float,
              sample_rate_hz: float) -> np.ndarray:
    """A linear ramp within each window (0 at the first sample, growing at ``*_drift_per_s`` along
    a random direction per window/sensor), simulating slow sensor bias drift."""
    b, t, _ = windows.shape
    elapsed_s = (np.arange(t) / sample_rate_hz)[None, :, None]
    out = windows.copy()
    acc_dir = rng.normal(size=(b, 1, 3))
    acc_dir /= np.linalg.norm(acc_dir, axis=-1, keepdims=True)
    gyr_dir = rng.normal(size=(b, 1, 3))
    gyr_dir /= np.linalg.norm(gyr_dir, axis=-1, keepdims=True)
    out[..., 0:3] += (acc_drift_per_s * elapsed_s * acc_dir).astype(out.dtype)
    out[..., 3:6] += (gyr_drift_per_s * elapsed_s * gyr_dir).astype(out.dtype)
    return out


def small_orientation_perturbation(windows: np.ndarray, rng: np.random.Generator, max_angle_deg: float) -> np.ndarray:
    """A small-angle random rotation per window (mounting imprecision), reusing the same rotation
    machinery as training augmentation, but at a magnitude meant to probe robustness, not to train
    invariance to it."""
    r = random_rotation_matrices(len(windows), rng, max_angle_deg)
    return rotate_windows(windows, r)


def make_perturbations(cfg: dict[str, Any], sample_rate_hz: float) -> dict[str, PerturbFn]:
    """Build the named perturbation functions from ``configs/member1.yaml``'s ``robustness`` section."""
    return {
        "sensor_noise": lambda w, rng: add_noise(w, rng, cfg["noise"]["acc_std_mps2"], cfg["noise"]["gyr_std_rads"]),
        "vibration": lambda w, rng: add_noise(w, rng, cfg["vibration"]["acc_std_mps2"], cfg["vibration"]["gyr_std_rads"]),
        "sensor_bias": lambda w, rng: add_bias(w, rng, cfg["bias"]["acc_bias_std_mps2"], cfg["bias"]["gyr_bias_std_rads"]),
        "sensor_drift": lambda w, rng: add_drift(w, rng, cfg["drift"]["acc_drift_mps2_per_s"],
                                                 cfg["drift"]["gyr_drift_rads_per_s"], sample_rate_hz),
        "orientation": lambda w, rng: small_orientation_perturbation(w, rng, cfg["orientation"]["max_angle_deg"]),
    }


def evaluate_perturbations(
    predict_fn: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]],
    windows: np.ndarray,
    y_true: np.ndarray,
    perturbations: dict[str, PerturbFn],
    seed: int,
) -> dict[str, Any]:
    """Run ``predict_fn`` (windows -> (mean, sigma)) on the clean windows and each perturbation.

    Returns ``{"clean": report, <perturbation_name>: report, ...}`` where each report has
    ``regression`` (MAE/RMSE/R2) and ``uncertainty`` (calibration) keys, from
    :mod:`src.evaluation.metrics`. Each perturbation gets its own seeded, reproducible RNG stream
    derived from ``seed`` and its name.
    """
    from src.evaluation.metrics import calibration_report, regression_metrics

    def _report(pred_windows: np.ndarray) -> dict[str, Any]:
        mean, sigma = predict_fn(pred_windows)
        return {"regression": regression_metrics(y_true, mean), "uncertainty": calibration_report(y_true, mean, sigma)}

    out = {"clean": _report(windows)}
    for name, fn in perturbations.items():
        rng = np.random.default_rng([seed, abs(hash(name)) % (2**31)])
        out[name] = _report(fn(windows, rng))
    return out
