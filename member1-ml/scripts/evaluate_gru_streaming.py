"""Evaluate the streaming-trained GRU (scripts/train_gru_streaming.py) in its NATIVE mode: hidden
state carried across an entire test session, reset only at genuine session boundaries -- never
mid-session, unlike a memoryless per-window evaluation (which is unfair to a model this deliberately
is not stateless; see docs/gru_velocity.md). Reports overall + regime metrics on every real 10 Hz
test row (not just window-end points), which streaming inference naturally produces predictions for.

Usage:
    python scripts/evaluate_gru_streaming.py --checkpoint experiments/m1_gru_stream2_gru_w20/best.pt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.pipeline import load_config, prepare_data  # noqa: E402
from src.data.windowing import session_starts  # noqa: E402
from src.evaluation.metrics import regression_metrics  # noqa: E402
from src.training.train import load_checkpoint, resolve_device  # noqa: E402
from scripts.evaluate_regimes import regime_masks  # noqa: E402
from scripts.train_gru_streaming import predict_session_streaming, session_ranges  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--window", type=int, default=20, help="regime-classification window (informational only)")
    p.add_argument("--device", default="cpu")
    args = p.parse_args()

    cfg = load_config(args.config)
    device = resolve_device(args.device)
    data = prepare_data(cfg, ROOT)
    test = data.subsets["test"]

    model, payload = load_checkpoint(args.checkpoint, map_location=device)
    model.to(device)
    model.eval()
    print(f"Streaming eval: {args.checkpoint} (arch={payload['arch']})")

    all_pred, all_true, all_idx = [], [], []
    for s, e in session_ranges(test.session_id):
        pred = predict_session_streaming(model, test.imu[s:e], device)
        all_pred.append(pred)
        all_true.append(test.target[s:e])
        all_idx.append(np.arange(s, e))
    pred = np.concatenate(all_pred)
    true = np.concatenate(all_true)
    finite = np.isfinite(true)
    pred, true = pred[finite], true[finite]

    overall = regression_metrics(true, pred)
    print(f"  overall (streaming, every row) n={overall['n']} MAE={overall['mae_mps']:.3f} "
          f"RMSE={overall['rmse_mps']:.3f} R2={overall['r2']:.3f}")

    # Regime breakdown: classify each row by the SAME criterion as evaluate_regimes.py, using a
    # window of context ending at that row (falls back to "moving_other" near a session start).
    ends_within_session = []
    win = args.window
    for s, e in session_ranges(test.session_id):
        if e - s >= win:
            ends_within_session.append(np.arange(s + win - 1, e))
    ends_full = np.concatenate(ends_within_session)
    full_pred = np.concatenate(all_pred)
    full_true = test.target
    for name, m in regime_masks(test.target, ends_full, win).items():
        idx = ends_full[m]
        idx = idx[np.isfinite(full_true[idx])]
        if idx.size == 0:
            continue
        rm = regression_metrics(full_true[idx], full_pred[idx])
        print(f"  {name:14s} n={rm['n']:7d} MAE={rm['mae_mps']:.3f} RMSE={rm['rmse_mps']:.3f} R2={rm['r2']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
