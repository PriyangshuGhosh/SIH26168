"""Milestone 2: train and evaluate causal CNN/TCN speed models, compare with the Milestone 1 baselines.

Usage:
    python scripts/run_training.py [--config configs/member1.yaml] [--archs cnn tcn] [--windows 20 40]
                                   [--max-epochs N] [--device auto|cpu|cuda] [--tag m2]

For every (arch, window) run, ``experiments/<tag>_<arch>_w<window>/`` receives:
    best.pt              best-validation-MAE checkpoint (model config + fitted normalisation)
    history.csv/.json    per-epoch training loss and validation metrics
    metrics.json         full train/val/test metrics of the best checkpoint
    training_curves.png, test_timeseries.png

``output.neural_results_dir`` receives the cross-run summary (summary.csv, results.json,
best_model.json) and comparison plots against ``output.results_dir``/results.json (baselines).
The test split is only evaluated with the best checkpoint of each run; model selection across
runs uses validation MAE.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.augmentation import AUGMENTATION_POLICIES, build_augmentation, representation_transform  # noqa: E402
from src.data.pipeline import PreparedData, load_config, prepare_data, split_window_ends, with_uncertainty, write_csv, write_json  # noqa: E402
from src.data.splits import SPLIT_NAMES  # noqa: E402
from src.data.windowing import gather_windows  # noqa: E402
from src.evaluation import plots  # noqa: E402
from src.evaluation.evaluate import evaluate_split, evaluate_split_uncertainty  # noqa: E402
from src.evaluation.metrics import regression_metrics  # noqa: E402
from src.models.tcn_velocity import build_model, count_parameters, fit_normalization  # noqa: E402
from src.training.train import (  # noqa: E402
    amp_dtype, load_checkpoint, predict_indexed, predict_indexed_uncertainty, predict_windows,
    predict_windows_uncertainty, resolve_device, seed_everything, train_model,
)

BASELINES_FOR_COMPARISON = ("constant_mean", "ridge_features", "physics_integration")


def run_one(cfg: dict[str, Any], data: PreparedData, arch: str, window: int, ends: dict[str, np.ndarray],
            train_windows: np.ndarray, val_windows: np.ndarray, device: torch.device, run_dir: Path,
            evaluate_test: bool = True) -> dict[str, Any]:
    """Train one (arch, window) config and evaluate it on train/val (always) and test (only if
    ``evaluate_test``). Exploratory runs that must not touch the test set (augmentation-policy
    comparisons, non-final ablations) should pass ``evaluate_test=False``."""
    tcfg, seed = cfg["training"], int(cfg["seed"])
    subsets = data.subsets
    y = {s: subsets[s].target[ends[s]].astype(np.float64) for s in (SPLIT_NAMES if evaluate_test else ("train", "val"))}

    seed_everything(seed, bool(tcfg["deterministic"]))
    model_cfg = cfg["models"][arch]
    model = build_model(arch, model_cfg)
    # normalisation fitted on training rows / training labels only
    model.set_normalization(*fit_normalization(subsets["train"].imu, y["train"]))
    n_params = count_parameters(model)
    print(f"\n--- {arch.upper()} | window {window} ({window / cfg['data']['sample_rate_hz']:g} s) | {n_params} parameters | "
          f"receptive field {model.receptive_field} | uncertainty={model.uncertainty} | device {device} ---")

    policy = tcfg.get("augmentation_policy", "so3")
    augment_fn = build_augmentation(policy, cfg["augmentation"]["so3_rotation"], cfg["augmentation"]["yaw_rotation"])
    repr_fn = representation_transform(policy)
    # augment_fn (when set) re-applies repr_fn itself every epoch (needed for "gravity_yaw", whose
    # alignment must be recomputed from each epoch's un-rotated-yet windows); train_x therefore
    # stays raw whenever an augment_fn will run, and only gets repr_fn applied when there is none.
    train_x = train_windows if augment_fn is not None else repr_fn(train_windows)
    val_x = repr_fn(val_windows)  # val is never augmented, but the (deterministic) representation transform always applies
    ckpt = run_dir / "best.pt"
    t0 = time.time()
    history = train_model(model, arch, model_cfg, train_x, y["train"], val_x, y["val"], tcfg, augment_fn, seed,
                          device, ckpt)
    train_time = time.time() - t0

    # evaluate the best checkpoint reloaded from disk
    best, payload = load_checkpoint(ckpt, map_location=device)
    best.to(device)
    dtype = amp_dtype(device, tcfg["amp"])
    bs = int(tcfg["eval_batch_size"])
    t1 = time.time()
    if best.uncertainty:
        preds = {"train": predict_windows_uncertainty(best, train_x, device, bs, dtype),
                 "val": predict_windows_uncertainty(best, val_x, device, bs, dtype)}
        if evaluate_test:
            preds["test"] = predict_indexed_uncertainty(best, subsets["test"].imu, ends["test"], window, device, bs, dtype,
                                                        transform=repr_fn)
        metrics = {"train": {"overall": regression_metrics(y["train"], preds["train"][0])},
                   "val": evaluate_split_uncertainty(subsets["val"], ends["val"], *preds["val"], cfg["evaluation"])}
        if evaluate_test:
            metrics["test"] = evaluate_split_uncertainty(subsets["test"], ends["test"], *preds["test"], cfg["evaluation"])
        test_pred = preds["test"][0] if evaluate_test else None
    else:
        preds = {"train": predict_windows(best, train_x, device, bs, dtype), "val": predict_windows(best, val_x, device, bs, dtype)}
        if evaluate_test:
            preds["test"] = predict_indexed(best, subsets["test"].imu, ends["test"], window, device, bs, dtype, transform=repr_fn)
        metrics = {"train": {"overall": regression_metrics(y["train"], preds["train"])},
                   "val": evaluate_split(subsets["val"], ends["val"], preds["val"], cfg["evaluation"])}
        if evaluate_test:
            metrics["test"] = evaluate_split(subsets["test"], ends["test"], preds["test"], cfg["evaluation"])
        test_pred = preds.get("test")
    eval_time = time.time() - t1
    info = {"arch": arch, "window": window, "n_parameters": n_params, "receptive_field": model.receptive_field,
            "uncertainty": best.uncertainty, "augmentation_policy": policy, "loss": tcfg["loss"],
            "best_epoch": payload["epoch"], "epochs_run": len(history), "train_time_s": train_time,
            "eval_time_s": eval_time, "checkpoint": str(ckpt.relative_to(ROOT)).replace("\\", "/"),
            "device": str(device), "amp_dtype": str(dtype), "model_cfg": model_cfg, "evaluate_test": evaluate_test}

    write_csv(history, run_dir / "history.csv")
    write_json(history, run_dir / "history.json")
    write_json({"info": info, "metrics": metrics}, run_dir / "metrics.json")
    plots.plot_training_curves(history, f"{arch.upper()}, window {window}: training", run_dir / "training_curves.png")
    if evaluate_test:
        test_sub = subsets["test"]
        plots.plot_prediction_timeseries(test_sub.session_id[ends["test"]], test_sub.t_session_s[ends["test"]], y["test"],
                                         {arch: test_pred}, f"{arch.upper()} w{window} test", run_dir / "test_timeseries.png")
    for s in metrics:
        o = metrics[s]["overall"]
        print(f"  {arch:4s} w{window} {s:5s} n={o['n']:7d} MAE={o['mae_mps']:.3f} m/s ({o['mae_kmh']:.2f} km/h) "
              f"RMSE={o['rmse_mps']:.3f} R2={o['r2']:.3f}")
    print(f"  best epoch {payload['epoch']}/{len(history)}, train time {train_time:.1f} s")
    return {"info": info, "metrics": metrics, "test_pred": test_pred}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    parser.add_argument("--archs", nargs="+", default=None)
    parser.add_argument("--windows", nargs="+", type=int, default=None)
    parser.add_argument("--max-epochs", type=int, default=None, help="override training.max_epochs (e.g. smoke runs)")
    parser.add_argument("--device", default=None, help="override training.device")
    parser.add_argument("--tag", default="m2", help="prefix for experiment directories")
    parser.add_argument("--augmentation", choices=list(AUGMENTATION_POLICIES), default=None,
                        help="override training.augmentation_policy")
    parser.add_argument("--no-so3", action="store_true", help="deprecated alias for --augmentation none")
    parser.add_argument("--uncertainty", action="store_true",
                        help="build the selected archs with a heteroscedastic uncertainty head and train with NLL loss")
    parser.add_argument("--results-dir", default=None, help="override output.neural_results_dir")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.max_epochs is not None:
        cfg["training"]["max_epochs"] = args.max_epochs
    if args.device is not None:
        cfg["training"]["device"] = args.device
    if args.no_so3:
        cfg["training"]["augmentation_policy"] = "none"
    if args.augmentation is not None:
        cfg["training"]["augmentation_policy"] = args.augmentation
    if args.uncertainty:
        cfg["training"]["loss"] = "nll"
        cfg = with_uncertainty(cfg, True)
    if args.results_dir is not None:
        cfg["output"]["neural_results_dir"] = args.results_dir
    archs = args.archs or cfg["training"]["archs"]
    windows = args.windows or cfg["windowing"]["window_sizes"]
    device = resolve_device(cfg["training"]["device"])
    exp_dir, out_dir = ROOT / cfg["output"]["experiments_dir"], ROOT / cfg["output"]["neural_results_dir"]

    baseline_path = ROOT / cfg["output"]["results_dir"] / "results.json"
    baselines = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.is_file() else None
    if baselines is None:
        print(f"WARNING: {baseline_path} not found; run scripts/run_baselines.py for the baseline comparison")

    data = prepare_data(cfg, ROOT)
    results: dict[str, Any] = {
        "config": cfg, "tag": args.tag, "split": data.split_info(),
        "environment": {"python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__,
                        "device": str(device), "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None},
        "window_counts": {}, "runs": {}, "metrics": {},
    }
    summary: list[dict[str, Any]] = []
    for window in windows:
        ends = split_window_ends(data.subsets, window, cfg)
        counts = {s: int(len(e)) for s, e in ends.items()}
        results["window_counts"][str(window)] = counts
        if baselines is not None and baselines["window_counts"].get(str(window)) != counts:
            raise RuntimeError(f"window counts {counts} differ from baseline run {baselines['window_counts'].get(str(window))}; "
                               "re-run baselines so the comparison uses identical windows")
        print(f"\n=== window = {window} samples: {counts} ===")
        train_windows = gather_windows(data.subsets["train"].imu, ends["train"], window)  # [N, T, 6], IMU only
        val_windows = gather_windows(data.subsets["val"].imu, ends["val"], window)
        results["metrics"][str(window)] = {}
        test_preds = {}
        for arch in archs:
            run_dir = exp_dir / f"{args.tag}_{arch}_w{window}"
            r = run_one(cfg, data, arch, window, ends, train_windows, val_windows, device, run_dir)
            results["runs"][f"{arch}_w{window}"] = r["info"]
            results["metrics"][str(window)][arch] = r["metrics"]
            test_preds[arch] = r["test_pred"]
            for s in SPLIT_NAMES:
                summary.append({"window_samples": window, "window_s": window / cfg["data"]["sample_rate_hz"], "model": arch,
                                "split": s, "n_parameters": r["info"]["n_parameters"], "best_epoch": r["info"]["best_epoch"],
                                "train_time_s": r["info"]["train_time_s"], **r["metrics"][s]["overall"]})

        # comparison plots for this window
        out_dir.mkdir(parents=True, exist_ok=True)
        test_sub = data.subsets["test"]
        y_test = test_sub.target[ends["test"]].astype(np.float64)
        plots.plot_prediction_timeseries(test_sub.session_id[ends["test"]], test_sub.t_session_s[ends["test"]], y_test,
                                         test_preds, f"CNN vs TCN, w{window}, test", out_dir / f"test_timeseries_w{window}.png")
        if baselines is not None:
            base_w = baselines["metrics"][str(window)]
            compare = {m: base_w[m] for m in ("ridge_features", "physics_integration")}
            compare.update(results["metrics"][str(window)])
            plots.plot_breakdown_comparison({m: v["test"] for m, v in compare.items()}, "by_speed_bin_mps",
                                            f"Test MAE per speed bin, window {window}", "true speed bin (m/s)",
                                            out_dir / f"test_mae_by_speed_bin_w{window}.png")
            plots.plot_breakdown_comparison({m: v["test"] for m, v in compare.items()}, "by_trip",
                                            f"Test MAE per trip, window {window}", "trip", out_dir / f"test_mae_by_trip_w{window}.png")
            plots.plot_breakdown_comparison({m: v["test"] for m, v in compare.items()}, "stationary_vs_moving",
                                            f"Test MAE stationary vs moving, window {window}", "", out_dir / f"test_mae_stationary_moving_w{window}.png")

    # best neural model: selected on validation MAE only
    best_key = min(results["runs"], key=lambda k: results["metrics"][str(results["runs"][k]["window"])]
                   [results["runs"][k]["arch"]]["val"]["overall"]["mae_mps"])
    best_info = results["runs"][best_key]
    best_metrics = results["metrics"][str(best_info["window"])][best_info["arch"]]
    results["best_model"] = {"run": best_key, "selected_by": "validation MAE", **best_info,
                             "val": best_metrics["val"]["overall"], "test": best_metrics["test"]["overall"]}
    if baselines is not None:
        comparison = []
        for w in map(str, windows):
            for m in BASELINES_FOR_COMPARISON:
                for s in ("val", "test"):
                    comparison.append({"window_samples": int(w), "model": m, "split": s, **baselines["metrics"][w][m][s]["overall"]})
            for m in archs:
                for s in ("val", "test"):
                    comparison.append({"window_samples": int(w), "model": m, "split": s, **results["metrics"][w][m][s]["overall"]})
        write_csv(comparison, out_dir / "comparison_with_baselines.csv")
        merged = {w: {**{m: baselines["metrics"][w][m] for m in BASELINES_FOR_COMPARISON}, **results["metrics"][w]}
                  for w in map(str, windows)}
        plots.plot_model_comparison(merged, list(BASELINES_FOR_COMPARISON) + list(archs), out_dir / "mae_comparison.png")

    results["summary"] = summary
    write_csv(summary, out_dir / "summary.csv")
    write_json(results, out_dir / "results.json")
    write_json(results["best_model"], out_dir / "best_model.json")
    b = results["best_model"]
    print(f"\nBest neural model (by validation MAE): {best_key}  val MAE={b['val']['mae_mps']:.3f}  "
          f"test MAE={b['test']['mae_mps']:.3f}  checkpoint={b['checkpoint']}")
    print(f"Saved results to {out_dir} and runs to {exp_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
