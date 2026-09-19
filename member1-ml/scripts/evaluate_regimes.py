"""Regime-breakdown comparison of Member 1 checkpoints on the test split: stationary, accelerating,
braking, and -- the regime that drives long-GNSS-blackout drift -- steady speed (moving, but with
little within-window speed change). See docs/gru_velocity.md for why this breakdown exists.

Usage:
    python scripts/evaluate_regimes.py --checkpoints experiments/production2_cnn_mag_w20/best.pt \\
        experiments/m1_gru_gru_w20/best.pt --window 20 --device cpu
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.pipeline import load_config, prepare_data, split_window_ends  # noqa: E402
from src.evaluation.metrics import regression_metrics  # noqa: E402
from src.training.train import (  # noqa: E402
    amp_dtype, load_checkpoint, predict_indexed, predict_indexed_uncertainty, resolve_device,
)

STEADY_WINDOW_SPEED_RANGE_MPS = 0.5  # max-min target speed inside the window
STATIONARY_MPS = 0.5
ACCEL_MPS = 0.5  # target[end] - target[start] threshold


def regime_masks(target: np.ndarray, ends: np.ndarray, window: int) -> dict[str, np.ndarray]:
    starts = ends - window + 1
    end_speed = target[ends]
    start_speed = target[starts]
    win_min = np.empty(len(ends))
    win_max = np.empty(len(ends))
    for i, (s, e) in enumerate(zip(starts, ends)):
        seg = target[s:e + 1]
        win_min[i], win_max[i] = seg.min(), seg.max()
    stationary = end_speed < STATIONARY_MPS
    moving = ~stationary
    delta = end_speed - start_speed
    steady = moving & ((win_max - win_min) < STEADY_WINDOW_SPEED_RANGE_MPS)
    accelerating = moving & (delta > ACCEL_MPS)
    braking = moving & (delta < -ACCEL_MPS)
    return {"stationary": stationary, "steady_speed": steady, "accelerating": accelerating,
            "braking": braking, "moving_other": moving & ~steady & ~accelerating & ~braking}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    p.add_argument("--checkpoints", nargs="+", required=True)
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--device", default="cpu")
    args = p.parse_args()

    cfg = load_config(args.config)
    device = resolve_device(args.device)
    data = prepare_data(cfg, ROOT)
    ends = split_window_ends(data.subsets, args.window, cfg)
    test = data.subsets["test"]
    y_test = test.target[ends["test"]].astype(np.float64)
    masks = regime_masks(test.target, ends["test"], args.window)

    print(f"Test split: n={len(y_test)} windows, window={args.window} samples "
          f"({args.window / cfg['data']['sample_rate_hz']:g} s)")
    for name, m in masks.items():
        print(f"  regime {name:14s} n={int(m.sum()):7d} ({100 * m.mean():5.1f}%)")
    print()

    for ckpt_path in args.checkpoints:
        model, payload = load_checkpoint(ckpt_path, map_location=device)
        model.to(device)
        dtype = amp_dtype(device, "off")
        arch = payload["arch"]
        print(f"=== {ckpt_path}  (arch={arch}, uncertainty={model.uncertainty}) ===")
        if model.uncertainty:
            mean, sigma = predict_indexed_uncertainty(model, test.imu, ends["test"], args.window, device, 4096, dtype)
        else:
            mean = predict_indexed(model, test.imu, ends["test"], args.window, device, 4096, dtype)
            sigma = None
        overall = regression_metrics(y_test, mean)
        row = f"  {'overall':14s} n={overall['n']:7d} MAE={overall['mae_mps']:.3f} RMSE={overall['rmse_mps']:.3f} R2={overall['r2']:.3f}"
        if sigma is not None:
            row += f"  sigma_mean={float(np.mean(sigma)):.3f}"
        print(row)
        for name, m in masks.items():
            if m.sum() == 0:
                continue
            rm = regression_metrics(y_test[m], mean[m])
            row = f"  {name:14s} n={rm['n']:7d} MAE={rm['mae_mps']:.3f} RMSE={rm['rmse_mps']:.3f} R2={rm['r2']:.3f}"
            if sigma is not None:
                row += f"  sigma_mean={float(np.mean(sigma[m])):.3f}"
            print(row)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
