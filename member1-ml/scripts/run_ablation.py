"""Consolidate every ablation already run across Milestones 2 and 3 into one table.

Usage:
    python scripts/run_ablation.py [--config configs/member1.yaml] [--out results/ablation]

This does NOT retrain anything -- every number here already exists on disk, written by
``scripts/run_training.py`` and ``scripts/run_uncertainty.py`` in earlier milestones (see
``docs/experiments.md`` for the narrative). It only reads their JSON outputs and assembles a single
comparison table, three ablation axes:

  1. **Window size** (2 s vs 4 s), from ``results/neural/results.json`` (SO(3) augmentation, the
     Milestone 2 default) at both window sizes, on validation and test.
  2. **Augmentation on/off**, from ``results/neural/results.json`` (SO(3)) vs
     ``results/neural_ablation_no_so3/results.json`` (none), at each window size.
  3. **Point loss vs heteroscedastic NLL loss**, for the final (cnn, 4 s, yaw) config, from
     ``results/uncertainty/results.json``'s phase 3 (validation only -- the point-loss variant was
     never evaluated on test, since it exists purely to isolate the accuracy cost, if any, of the
     uncertainty head, not as a deployment candidate).

Requires ``results/neural/results.json``, ``results/neural_ablation_no_so3/results.json`` and
``results/uncertainty/results.json`` to already exist (run ``scripts/run_training.py`` with and
without ``--no-so3``, then ``scripts/run_uncertainty.py``, first).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.pipeline import load_config, write_csv, write_json  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found -- run the milestone scripts that produce it first "
                                "(see this script's module docstring)")
    return json.loads(path.read_text(encoding="utf-8"))


def window_size_ablation(neural: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for window_s, metrics_by_arch in neural["metrics"].items():
        for arch, metrics in metrics_by_arch.items():
            for split in ("val", "test"):
                o = metrics[split]["overall"]
                rows.append({"ablation": "window_size", "window_samples": int(window_s), "arch": arch,
                            "augmentation": "so3", "split": split, "mae_mps": o["mae_mps"],
                            "rmse_mps": o["rmse_mps"], "r2": o["r2"]})
    return rows


def augmentation_on_off_ablation(neural: dict[str, Any], neural_noaug: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for augmentation, results in (("so3", neural), ("none", neural_noaug)):
        for window_s, metrics_by_arch in results["metrics"].items():
            for arch, metrics in metrics_by_arch.items():
                for split in ("val", "test"):
                    o = metrics[split]["overall"]
                    rows.append({"ablation": "augmentation_on_off", "window_samples": int(window_s), "arch": arch,
                                "augmentation": augmentation, "split": split, "mae_mps": o["mae_mps"],
                                "rmse_mps": o["rmse_mps"], "r2": o["r2"]})
    return rows


def augmentation_policy_ablation(uncertainty_results: dict[str, Any]) -> list[dict[str, Any]]:
    table = uncertainty_results["phase1_augmentation_comparison"]["table"]
    chosen = uncertainty_results["phase1_augmentation_comparison"]["chosen_policy"]
    rows = []
    for policy, entry in table.items():
        v = entry["val"]
        rows.append({"ablation": "augmentation_policy", "policy": policy, "split": "val",
                    "mae_mps": v["mae_mps"], "rmse_mps": v["rmse_mps"], "r2": v["r2"], "chosen": policy == chosen})
    return rows


def loss_ablation(uncertainty_results: dict[str, Any]) -> list[dict[str, Any]]:
    p3 = uncertainty_results["phase3_point_vs_nll_ablation"]
    rows = []
    for loss, key in (("nll", "nll"), ("huber", "point")):
        o = p3[key]
        rows.append({"ablation": "loss", "loss": loss, "split": "val", "mae_mps": o["mae_mps"],
                    "rmse_mps": o["rmse_mps"], "r2": o["r2"]})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    parser.add_argument("--out", default=str(ROOT / "results" / "ablation"))
    args = parser.parse_args()

    cfg = load_config(args.config)  # validated for consistency; not otherwise used (no retraining here)
    out_dir = Path(args.out)

    neural = load_json(ROOT / cfg["output"]["neural_results_dir"] / "results.json")
    neural_noaug = load_json(ROOT / "results" / "neural_ablation_no_so3" / "results.json")
    uncertainty = load_json(ROOT / cfg["output"]["uncertainty_results_dir"] / "results.json")

    tables = {
        "window_size": window_size_ablation(neural),
        "augmentation_on_off": augmentation_on_off_ablation(neural, neural_noaug),
        "augmentation_policy": augmentation_policy_ablation(uncertainty),
        "loss": loss_ablation(uncertainty),
    }

    print("Ablation summary (all numbers already computed by earlier milestone runs; nothing retrained here):")
    for rows in tables.values():
        for r in rows:
            extra = " ".join(f"{k}={v}" for k, v in r.items() if k not in ("ablation", "mae_mps", "rmse_mps", "r2"))
            print(f"  [{r['ablation']:20s}] {extra:55s} MAE={r['mae_mps']:.3f} m/s  RMSE={r['rmse_mps']:.3f}  R2={r['r2']:.3f}")

    # each ablation axis has its own (heterogeneous) set of columns, so each gets its own CSV;
    # write_csv's DictWriter needs one fixed fieldname set per file.
    for name, rows in tables.items():
        write_csv(rows, out_dir / f"{name}.csv")
    write_json({"tables": tables, "sources": {
        "neural": "results/neural/results.json", "neural_ablation_no_so3": "results/neural_ablation_no_so3/results.json",
        "uncertainty": "results/uncertainty/results.json",
    }}, out_dir / "ablation_summary.json")
    print(f"\nSaved consolidated ablation summary to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
