"""Evaluate an already-trained Member 1 checkpoint on one or more data splits, without training,
retraining or selecting a model.

Usage:
    python scripts/run_evaluation.py [--config configs/member1.yaml]
                                     [--final-model-json results/uncertainty/final_model.json]
                                     [--checkpoint PATH --window N [--augmentation-policy yaw]]
                                     [--splits val test unseen] [--out PATH]

By default evaluates the Milestone 3 final checkpoint (``results/uncertainty/final_model.json``) on
val, test and the unseen-group diagnostic (Vfa01/Vta1a/Vta1b/Y1) -- reproducing the same numbers
already reported in ``docs/experiments.md``, without rerunning ``scripts/run_uncertainty.py``'s full
training pipeline. Pass ``--checkpoint``/``--window`` to evaluate a different, already-trained
checkpoint (e.g. an earlier Milestone 2 run, or a future LOVO fold's checkpoint) on demand.

Reuses ``src.evaluation.evaluate``/``src.evaluation.metrics`` throughout -- no metric logic is
reimplemented here. The test split is only ever read, never fit or selected on; evaluating it again
here does not change which model was chosen (that happened once, in Milestone 3).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.augmentation import representation_transform  # noqa: E402
from src.data.pipeline import load_config, prepare_data, split_window_ends, write_json  # noqa: E402
from src.data.windowing import window_end_indices  # noqa: E402
from src.evaluation.evaluate import evaluate_split, evaluate_split_uncertainty  # noqa: E402
from src.training.train import (  # noqa: E402
    amp_dtype, load_checkpoint, predict_indexed, predict_indexed_uncertainty, resolve_device,
)

SPLIT_CHOICES = ("train", "val", "test", "unseen")


def resolve_checkpoint(args) -> tuple[Path, int, str]:
    if args.checkpoint is not None:
        if args.window is None:
            raise SystemExit("--window is required when --checkpoint is given directly")
        return Path(args.checkpoint), args.window, args.augmentation_policy or "yaw"
    info = json.loads(Path(args.final_model_json).read_text(encoding="utf-8"))
    return ROOT / info["checkpoint"], int(info["window"]), info["augmentation_policy"]


def evaluate_unseen_groups(cfg: dict[str, Any], data, model, window: int, device, dtype, bs: int, transform) -> dict[str, Any] | None:
    """Diagnostic-only evaluation on trips that match no split rule (never trained, validated,
    selected or tested on) -- see ``docs/data_protocol.md``."""
    unassigned = data.split.unassigned_trips
    if not unassigned:
        return None
    mask = np.isin(data.dataset.trip_id, unassigned)
    sub = data.dataset.subset(mask)
    ends = window_end_indices(sub, window, cfg["windowing"]["eval_stride"], cfg["data"]["sample_rate_hz"], cfg["data"]["dt_tolerance_s"])
    if len(ends) == 0:
        return None
    if model.uncertainty:
        mean, sigma = predict_indexed_uncertainty(model, sub.imu, ends, window, device, bs, dtype, transform=transform)
        report = evaluate_split_uncertainty(sub, ends, mean, sigma, cfg["evaluation"])
    else:
        mean = predict_indexed(model, sub.imu, ends, window, device, bs, dtype, transform=transform)
        report = evaluate_split(sub, ends, mean, cfg["evaluation"])
    report["trips"] = unassigned
    report["n_windows"] = int(len(ends))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    parser.add_argument("--final-model-json", default=str(ROOT / "results" / "uncertainty" / "final_model.json"))
    parser.add_argument("--checkpoint", default=None, help="evaluate this .pt directly instead of final_model.json's entry")
    parser.add_argument("--window", type=int, default=None, help="required with --checkpoint")
    parser.add_argument("--augmentation-policy", default=None, help="representation policy for --checkpoint (default: yaw)")
    parser.add_argument("--splits", nargs="+", choices=SPLIT_CHOICES, default=["val", "test", "unseen"])
    parser.add_argument("--device", default=None)
    parser.add_argument("--out", default=None, help="output JSON path (default: results/evaluation/<checkpoint-stem>.json)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.device is not None:
        cfg["training"]["device"] = args.device
    device = resolve_device(cfg["training"]["device"])

    ckpt_path, window, policy = resolve_checkpoint(args)
    print(f"Checkpoint: {ckpt_path}  window={window}  policy={policy!r}  device={device}")
    model, payload = load_checkpoint(ckpt_path, map_location=device)
    model.to(device)
    dtype = amp_dtype(device, cfg["training"]["amp"])
    bs = int(cfg["training"]["eval_batch_size"])
    transform = representation_transform(policy)

    data = prepare_data(cfg, ROOT, verbose=False)
    ends = split_window_ends(data.subsets, window, cfg)

    report: dict[str, Any] = {"checkpoint": str(ckpt_path), "arch": payload["arch"], "window": window,
                              "augmentation_policy": policy, "uncertainty": model.uncertainty, "device": str(device)}
    for split in args.splits:
        if split == "unseen":
            u = evaluate_unseen_groups(cfg, data, model, window, device, dtype, bs, transform)
            if u is None:
                print("  unseen: no unassigned trips in this dataset, skipped")
                continue
            report["unseen"] = u
            o = u["overall"]
        else:
            sub, e = data.subsets[split], ends[split]
            if model.uncertainty:
                mean, sigma = predict_indexed_uncertainty(model, sub.imu, e, window, device, bs, dtype, transform=transform)
                report[split] = evaluate_split_uncertainty(sub, e, mean, sigma, cfg["evaluation"])
            else:
                mean = predict_indexed(model, sub.imu, e, window, device, bs, dtype, transform=transform)
                report[split] = evaluate_split(sub, e, mean, cfg["evaluation"])
            o = report[split]["overall"]
        print(f"  {split:6s} n={o['n']:7d} MAE={o['mae_mps']:.3f} m/s ({o['mae_kmh']:.2f} km/h) RMSE={o['rmse_mps']:.3f} R2={o['r2']:.3f}")

    out_path = Path(args.out) if args.out else ROOT / "results" / "evaluation" / f"{ckpt_path.stem}.json"
    write_json(report, out_path)
    print(f"Saved evaluation report to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
