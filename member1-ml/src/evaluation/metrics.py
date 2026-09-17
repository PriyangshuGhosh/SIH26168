"""Velocity regression metrics, plus (Milestone 3) predictive-uncertainty calibration.

Units: MAE and RMSE are in m/s (``*_kmh`` variants = m/s x 3.6); R^2 is dimensionless; sigma
(predictive standard deviation) is in m/s. All functions ignore nothing silently: inputs must be
finite and equally shaped, and sigma must be strictly positive.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import norm

MPS_TO_KMH = 3.6
DEFAULT_CALIBRATION_LEVELS: tuple[float, ...] = (0.5, 0.68, 0.8, 0.9, 0.95, 0.99)


def _check(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y_true = np.asarray(y_true, dtype=np.float64).ravel()
    y_pred = np.asarray(y_pred, dtype=np.float64).ravel()
    if y_true.shape != y_pred.shape:
        raise ValueError(f"shape mismatch {y_true.shape} vs {y_pred.shape}")
    if not (np.isfinite(y_true).all() and np.isfinite(y_pred).all()):
        raise ValueError("non-finite values in metric inputs")
    return y_true, y_pred


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    t, p = _check(y_true, y_pred)
    return float(np.mean(np.abs(t - p))) if t.size else float("nan")


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    t, p = _check(y_true, y_pred)
    return float(np.sqrt(np.mean((t - p) ** 2))) if t.size else float("nan")


def r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Coefficient of determination; NaN when the target has zero variance or is empty."""
    t, p = _check(y_true, y_pred)
    if t.size == 0:
        return float("nan")
    ss_tot = float(np.sum((t - t.mean()) ** 2))
    return float(1.0 - np.sum((t - p) ** 2) / ss_tot) if ss_tot > 0 else float("nan")


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    m = {"n": int(np.asarray(y_true).size), "mae_mps": mae(y_true, y_pred), "rmse_mps": rmse(y_true, y_pred),
         "r2": r2(y_true, y_pred)}
    m["mae_kmh"] = m["mae_mps"] * MPS_TO_KMH
    m["rmse_kmh"] = m["rmse_mps"] * MPS_TO_KMH
    return m


def metrics_by_group(y_true: np.ndarray, y_pred: np.ndarray, groups: np.ndarray) -> dict[str, dict[str, float]]:
    """Metrics per unique group label (e.g. trip_id or session_id)."""
    groups = np.asarray(groups).astype(str)
    return {g: regression_metrics(y_true[groups == g], y_pred[groups == g]) for g in sorted(set(groups))}


def metrics_stationary_moving(y_true: np.ndarray, y_pred: np.ndarray, threshold_mps: float = 0.5) -> dict[str, dict[str, float]]:
    """Split by true speed: stationary = ``y_true < threshold_mps``, moving otherwise."""
    stationary = np.asarray(y_true) < threshold_mps
    return {name: regression_metrics(y_true[m], y_pred[m]) for name, m in (("stationary", stationary), ("moving", ~stationary))}


def metrics_by_speed_bin(y_true: np.ndarray, y_pred: np.ndarray, edges_mps: list[float]) -> dict[str, dict[str, float]]:
    """Metrics per true-speed bin ``[lo, hi)``; empty bins are omitted."""
    out = {}
    for lo, hi in zip(edges_mps[:-1], edges_mps[1:]):
        m = (y_true >= lo) & (y_true < hi)
        if m.any():
            out[f"[{lo:g},{hi:g})"] = regression_metrics(y_true[m], y_pred[m])
    return out


def full_report(y_true: np.ndarray, y_pred: np.ndarray, groups: dict[str, np.ndarray], stationary_threshold_mps: float,
                speed_bins_mps: list[float]) -> dict[str, Any]:
    return {
        "overall": regression_metrics(y_true, y_pred),
        **{f"by_{name}": metrics_by_group(y_true, y_pred, g) for name, g in groups.items()},
        "stationary_vs_moving": metrics_stationary_moving(y_true, y_pred, stationary_threshold_mps),
        "by_speed_bin_mps": metrics_by_speed_bin(y_true, y_pred, speed_bins_mps),
    }


# --------------------------------------------------------------------------------- uncertainty


def _check_sigma(y_true: np.ndarray, mean: np.ndarray, sigma: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t, m = _check(y_true, mean)
    sigma = np.asarray(sigma, dtype=np.float64).ravel()
    if sigma.shape != t.shape:
        raise ValueError(f"shape mismatch: sigma {sigma.shape} vs y_true {t.shape}")
    if not np.isfinite(sigma).all():
        raise ValueError("non-finite sigma")
    if np.any(sigma <= 0):
        raise ValueError("sigma must be strictly positive")
    return t, m, sigma


def nll_gaussian(y_true: np.ndarray, mean: np.ndarray, sigma: np.ndarray) -> float:
    """Mean Gaussian negative log-likelihood (nats), in native (m/s) units. Lower is better."""
    t, m, s = _check_sigma(y_true, mean, sigma)
    if t.size == 0:
        return float("nan")
    var = s ** 2
    return float(np.mean(0.5 * (np.log(2.0 * math.pi * var) + (t - m) ** 2 / var)))


def coverage(y_true: np.ndarray, mean: np.ndarray, sigma: np.ndarray, z: float) -> float:
    """Fraction of points with ``|y_true - mean| <= z * sigma`` (the empirical interval coverage
    of the symmetric interval ``mean +/- z*sigma``)."""
    t, m, s = _check_sigma(y_true, mean, sigma)
    if t.size == 0:
        return float("nan")
    return float(np.mean(np.abs(t - m) <= z * s))


def sharpness(sigma: np.ndarray) -> dict[str, float]:
    """Summary of predicted uncertainty magnitude alone (no ground truth): smaller is "sharper",
    but sharpness only means calibration is efficient, not that it IS calibrated -- always read it
    together with :func:`calibration_report`'s coverage numbers."""
    sigma = np.asarray(sigma, dtype=np.float64).ravel()
    return {"mean_sigma_mps": float(np.mean(sigma)), "median_sigma_mps": float(np.median(sigma)),
            "min_sigma_mps": float(np.min(sigma)), "max_sigma_mps": float(np.max(sigma))}


def calibration_report(y_true: np.ndarray, mean: np.ndarray, sigma: np.ndarray,
                        nominal_levels: tuple[float, ...] | list[float] = DEFAULT_CALIBRATION_LEVELS) -> dict[str, Any]:
    """Full uncertainty report: NLL, sharpness, error/sigma correlation, and a reliability curve.

    For each two-sided nominal confidence level (e.g. 0.68 for "1 sigma"), the reliability curve
    compares the level's expected coverage against the actually observed coverage of the interval
    ``mean +/- z*sigma`` (``z`` = the Gaussian quantile of that level). A well-calibrated model has
    observed ~= expected at every level; observed < expected means the model is overconfident
    (sigma too small) and observed > expected means it is underconfident (sigma too large).
    """
    t, m, s = _check_sigma(y_true, mean, sigma)
    levels = {}
    for level in nominal_levels:
        z = float(norm.ppf(0.5 + level / 2.0))
        levels[f"{level:g}"] = {"z": z, "expected_coverage": float(level), "observed_coverage": coverage(t, m, s, z)}
    abs_err = np.abs(t - m)
    error_sigma_correlation = float(np.corrcoef(abs_err, s)[0, 1]) if len(t) > 1 and np.std(s) > 0 else float("nan")
    return {"n": int(t.size), "nll": nll_gaussian(t, m, s), **sharpness(s),
            "error_sigma_correlation": error_sigma_correlation, "levels": levels}
