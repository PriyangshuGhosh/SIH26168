"""Evaluation of speed predictions at window end points, shared by baselines and neural models."""
from __future__ import annotations

from typing import Any

import numpy as np

from src.data.dataset import ImuDataset
from src.evaluation.metrics import DEFAULT_CALIBRATION_LEVELS, calibration_report, full_report


def evaluate_split(sub: ImuDataset, ends: np.ndarray, pred: np.ndarray, eval_cfg: dict[str, Any]) -> dict[str, Any]:
    """Full metric report (overall, per trip, per session, stationary/moving, speed bins) in m/s and km/h."""
    y = sub.target[ends].astype(np.float64)
    if pred.shape != y.shape:
        raise ValueError(f"prediction shape {pred.shape} does not match {y.shape}")
    return full_report(y, pred, {"trip": sub.trip_id[ends], "session": sub.session_id[ends]},
                       eval_cfg["stationary_threshold_mps"], eval_cfg["speed_bins_mps"])


def evaluate_split_uncertainty(sub: ImuDataset, ends: np.ndarray, mean: np.ndarray, sigma: np.ndarray,
                               eval_cfg: dict[str, Any]) -> dict[str, Any]:
    """:func:`evaluate_split`'s report, plus an ``"uncertainty"`` key with the calibration report
    (NLL, sharpness, error/sigma correlation, reliability curve) from :mod:`src.evaluation.metrics`.
    """
    report = evaluate_split(sub, ends, mean, eval_cfg)
    y = sub.target[ends].astype(np.float64)
    levels = eval_cfg.get("calibration", {}).get("nominal_levels", DEFAULT_CALIBRATION_LEVELS)
    report["uncertainty"] = calibration_report(y, mean, sigma, levels)
    return report
