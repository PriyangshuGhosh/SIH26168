"""Milestone 1 baseline experiment: constant mean, ridge on window statistics, physics integration.

Usage:
    python scripts/run_baselines.py [--config configs/member1.yaml]

Outputs (under ``output.results_dir``):
    summary.csv         one row per (window, model, split) with MAE/RMSE/R^2
    results.json        full metrics (per trip/session, stationary vs moving, speed bins),
                        selected hyperparameters, split membership and window counts
    *.png               MAE overview, per-speed-bin MAE, test-session time series
"""
from __future__ import annotations

import argparse
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.augmentation import augment_so3  # noqa: E402
from src.data.pipeline import load_config, prepare_data, split_window_ends, write_csv, write_json  # noqa: E402
from src.data.splits import SPLIT_NAMES  # noqa: E402
from src.data.windowing import gather_windows  # noqa: E402
from src.evaluation.evaluate import evaluate_split  # noqa: E402
from src.evaluation.metrics import mae, regression_metrics  # noqa: E402
from src.models.baselines import (  # noqa: E402
    ConstantMeanBaseline, PhysicsIntegrationBaseline, RidgeFeatureBaseline,
)

EVAL_SPLITS = ("val", "test")


def run(cfg: dict[str, Any]) -> dict[str, Any]:
    seed = int(cfg["seed"])
    rng = np.random.default_rng(seed)
    data = prepare_data(cfg, ROOT)
    subsets = data.subsets

    wcfg, ecfg, bcfg = cfg["windowing"], cfg["evaluation"], cfg["baselines"]
    results: dict[str, Any] = {
        "config": cfg,
        "environment": {"python": platform.python_version(), "numpy": np.__version__},
        "split": data.split_info(),
        "window_counts": {}, "hyperparameters": {}, "metrics": {}, "predictions_for_plots": {},
    }
    summary_rows: list[dict[str, Any]] = []

    for window in wcfg["window_sizes"]:
        t0 = time.time()
        print(f"\n=== window = {window} samples ({window / cfg['data']['sample_rate_hz']:g} s) ===")
        ends = split_window_ends(subsets, window, cfg)
        results["window_counts"][str(window)] = {s: int(len(e)) for s, e in ends.items()}
        print("  windows:", results["window_counts"][str(window)])
        y = {s: subsets[s].target[ends[s]].astype(np.float64) for s in SPLIT_NAMES}
        train_windows = gather_windows(subsets["train"].imu, ends["train"], window)  # [B, T, 6]
        preds: dict[str, dict[str, np.ndarray]] = {}
        hp: dict[str, Any] = {}

        # A. constant mean
        const = ConstantMeanBaseline().fit(y["train"])
        preds[const.name] = {s: const.predict(len(y[s])) for s in SPLIT_NAMES}
        hp[const.name] = {"train_mean_mps": const.mean_}

        # B. ridge (alpha selected on validation MAE), optionally on SO(3)-augmented training windows
        variants = [("ridge_features", train_windows)]
        if bcfg["ridge"]["with_so3_augmentation"]:
            aug = cfg["augmentation"]["so3_rotation"]
            variants.append(("ridge_features_so3aug", augment_so3(train_windows, rng, aug["probability"], aug["max_angle_deg"])))
        for name, xw in variants:
            best = None
            val_scores = {}
            for alpha in bcfg["ridge"]["alphas"]:
                model = RidgeFeatureBaseline(alpha).fit(xw, y["train"])
                p_val = model.predict_indexed(subsets["val"].imu, ends["val"], window)
                val_scores[str(alpha)] = mae(y["val"], p_val)
                if best is None or val_scores[str(alpha)] < best[0]:
                    best = (val_scores[str(alpha)], model, p_val)
            _, model, p_val = best
            preds[name] = {"train": model.predict(xw), "val": p_val,
                           "test": model.predict_indexed(subsets["test"].imu, ends["test"], window)}
            hp[name] = {"alpha": model.alpha, "val_mae_by_alpha": val_scores}

        # C. physics integration (ZUPT/leak selected on training MAE)
        pcfg = bcfg["physics"]
        phys = PhysicsIntegrationBaseline(cfg["data"]["sample_rate_hz"], pcfg["gravity_tau_s"], pcfg["axis_tau_s"],
                                          pcfg["zupt_window_s"], zupt_gyr_std=pcfg["zupt_gyr_std"])
        phys.fit(subsets["train"], ends["train"], pcfg["zupt_acc_std_grid"], pcfg["leak_tau_s_grid"])
        preds[phys.name] = {s: phys.predict_rows(subsets[s])[ends[s]] for s in SPLIT_NAMES}
        hp[phys.name] = {"zupt_acc_std": phys.zupt_acc_std, "leak_tau_s": phys.leak_tau_s, "grid": phys.grid_results_}

        # evaluation
        results["hyperparameters"][str(window)] = hp
        results["metrics"][str(window)] = {}
        for model_name, by_split in preds.items():
            results["metrics"][str(window)][model_name] = {"train": {"overall": regression_metrics(y["train"], by_split["train"])}}
            for s in EVAL_SPLITS:
                results["metrics"][str(window)][model_name][s] = evaluate_split(subsets[s], ends[s], by_split[s], ecfg)
            for s in SPLIT_NAMES:
                o = results["metrics"][str(window)][model_name][s]["overall"]
                summary_rows.append({"window_samples": window, "window_s": window / cfg["data"]["sample_rate_hz"],
                                     "model": model_name, "split": s, "stride": wcfg["train_stride" if s == "train" else "eval_stride"],
                                     **o})
                print(f"  {model_name:24s} {s:5s} n={o['n']:7d} MAE={o['mae_mps']:.3f} m/s  RMSE={o['rmse_mps']:.3f} m/s  R2={o['r2']:.3f}")
        results["predictions_for_plots"][str(window)] = {
            "test_session_id": subsets["test"].session_id[ends["test"]],
            "test_t_s": subsets["test"].t_session_s[ends["test"]],
            "test_true": y["test"],
            "test_pred": {m: p["test"] for m, p in preds.items()},
        }
        print(f"  done in {time.time() - t0:.1f} s")

    results["summary"] = summary_rows
    return results


def save(results: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_data = results.pop("predictions_for_plots")
    write_csv(results["summary"], out_dir / "summary.csv")
    write_json(results, out_dir / "results.json")
    from src.evaluation.plots import plot_baselines  # matplotlib imported only when saving plots
    plot_baselines(results, plot_data, out_dir)
    print(f"\nSaved results to {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    args = parser.parse_args()
    cfg = load_config(args.config)
    results = run(cfg)
    save(results, ROOT / cfg["output"]["results_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
