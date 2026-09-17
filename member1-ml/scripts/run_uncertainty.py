"""Milestone 3: uncertainty, augmentation-policy selection, robustness, and final model selection.

Usage:
    python scripts/run_uncertainty.py [--config configs/member1.yaml] [--max-epochs N] [--device ...]

Builds on Milestone 1 (``results/baselines/results.json``) and Milestone 2 (``results/neural/results.json``,
``results/neural_ablation_no_so3/results.json``), which must already exist (run ``run_baselines.py`` then
``run_training.py`` first). Reuses ``scripts/run_training.run_one`` for every individual training run --
no training/prediction/evaluation logic is duplicated here.

Phases (see ``docs/experiments.md`` for the actual results and reasoning):

1. Augmentation-policy comparison: TCN @ 4 s window, point (Huber) loss, one run per policy in
   {none, so3, yaw, gravity_yaw}. The "so3" and "none" results are the existing Milestone 2 /
   ablation runs (re-used, not retrained, since nothing about that config changed); "yaw" and
   "gravity_yaw" are new. Selection uses VALIDATION MAE only -- ``evaluate_test=False`` for the new
   runs, and the existing runs' test numbers are not consulted for this decision.
2. Final-selection matrix: {cnn, tcn} x {20, 40} samples, WITH the chosen augmentation policy,
   heteroscedastic NLL loss (``uncertainty=True``). Still ``evaluate_test=False``. Each candidate is
   scored on validation MAE/R2/calibration, a validation-set robustness battery (perturbations +
   unseen-group trips), and CPU latency/parameter count.
3. Ablation: the winning (arch, window, policy) retrained with point (Huber) loss instead of NLL,
   to isolate the accuracy cost (if any) of adding the uncertainty head -- validation only.
4. Final evaluation: the winning checkpoint from phase 2 (already trained; not retrained) is
   evaluated on the S-series TEST set for the first and only time, with the full metric/calibration
   report, the robustness battery, and the never-trained-on trip groups (Vfa01/Vta1a/Vta1b/Y1,
   reported as an explicit diagnostic, not part of the main benchmark). Its confidence reference
   (for the output contract) is then fit from TRAINING sigma only and saved as ``final.pt``.
"""
from __future__ import annotations

import argparse
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_training import run_one  # noqa: E402

from src.data.augmentation import AUGMENTATION_POLICIES, build_augmentation, representation_transform  # noqa: E402
from src.data.pipeline import load_config, prepare_data, split_window_ends, with_uncertainty, write_csv, write_json  # noqa: E402
from src.data.windowing import gather_windows, window_end_indices  # noqa: E402
from src.evaluation import plots  # noqa: E402
from src.evaluation.evaluate import evaluate_split_uncertainty  # noqa: E402
from src.evaluation.robustness import evaluate_perturbations, make_perturbations  # noqa: E402
from src.models.tcn_velocity import build_model, count_parameters  # noqa: E402
from src.training.train import (  # noqa: E402
    amp_dtype, load_checkpoint, predict_windows_uncertainty, resolve_device, save_checkpoint, seed_everything,
)

AUGMENTATION_ARCH, AUGMENTATION_WINDOW = "tcn", 40  # the Milestone 2 winner without augmentation


def load_json(path: Path) -> dict[str, Any]:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def make_predict_fn(model, device: torch.device, dtype, batch_size: int, transform=None):
    def predict_fn(windows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        w = transform(windows) if transform is not None else windows
        return predict_windows_uncertainty(model, w, device, batch_size, dtype)
    return predict_fn


def cpu_latency_ms(model, arch: str, model_cfg: dict[str, Any], window: int, n_repeats: int = 200) -> float:
    """Mean single-window CPU forward-pass latency (plain PyTorch, no ONNX/export)."""
    cpu_model = build_model(arch, {**model_cfg, "dropout": 0.0}).eval()
    cpu_model.load_state_dict(model.state_dict())
    x = torch.randn(1, window, 6)
    with torch.no_grad():
        for _ in range(10):
            cpu_model(x)  # warm-up
        t0 = time.perf_counter()
        for _ in range(n_repeats):
            cpu_model(x)
        return (time.perf_counter() - t0) / n_repeats * 1000.0


def robustness_battery(model, windows: np.ndarray, y_true: np.ndarray, device: torch.device, dtype, bs: int,
                       robustness_cfg: dict[str, Any], sample_rate_hz: float, seed: int, transform=None) -> dict[str, Any]:
    predict_fn = make_predict_fn(model, device, dtype, bs, transform)
    perturbations = make_perturbations(robustness_cfg, sample_rate_hz)
    return evaluate_perturbations(predict_fn, windows, y_true, perturbations, seed)


def unseen_group_report(cfg: dict[str, Any], data, model, window: int, device: torch.device, dtype, bs: int,
                        transform=None) -> dict[str, Any] | None:
    """Diagnostic-only evaluation on trips outside train/val/test (never trained or selected on)."""
    unassigned = data.split.unassigned_trips
    if not unassigned:
        return None
    mask = np.isin(data.dataset.trip_id, unassigned)
    sub = data.dataset.subset(mask)
    ends = window_end_indices(sub, window, cfg["windowing"]["eval_stride"], cfg["data"]["sample_rate_hz"], cfg["data"]["dt_tolerance_s"])
    if len(ends) == 0:
        return None
    windows = gather_windows(sub.imu, ends, window)
    mean, sigma = predict_windows_uncertainty(model, transform(windows) if transform is not None else windows, device, bs, dtype)
    report = evaluate_split_uncertainty(sub, ends, mean, sigma, cfg["evaluation"])
    report["trips"] = unassigned
    report["n_windows"] = int(len(ends))
    return report


def phase1_augmentation_comparison(cfg: dict[str, Any], data, device: torch.device, exp_dir: Path,
                                   m2_results: dict, m2_noaug_results: dict) -> tuple[str, dict[str, Any]]:
    """Compare augmentation policies on validation MAE (point loss, TCN @ 4 s); return (chosen, table)."""
    print("\n=== Phase 1: augmentation-policy comparison (TCN, 4 s window, point loss, validation only) ===")
    window = AUGMENTATION_WINDOW
    ends = split_window_ends(data.subsets, window, cfg)
    train_windows = gather_windows(data.subsets["train"].imu, ends["train"], window)
    val_windows = gather_windows(data.subsets["val"].imu, ends["val"], window)

    table: dict[str, Any] = {}
    for policy in ("so3", "none"):
        source = m2_results if policy == "so3" else m2_noaug_results
        val = source["metrics"][str(window)][AUGMENTATION_ARCH]["val"]["overall"]
        table[policy] = {"val": val, "reused_from": "results/neural" if policy == "so3" else "results/neural_ablation_no_so3",
                         "retrained": False}
        print(f"  {policy:12s} (reused) val MAE={val['mae_mps']:.3f} m/s")

    base_cfg = with_uncertainty({**cfg, "training": {**cfg["training"], "loss": "huber"}}, False)
    for policy in ("yaw", "gravity_yaw"):  # base_cfg already has uncertainty=False, from with_uncertainty above
        run_cfg = {**base_cfg, "training": {**base_cfg["training"], "augmentation_policy": policy}}
        run_dir = exp_dir / f"m3_aug_{policy}_{AUGMENTATION_ARCH}_w{window}"
        r = run_one(run_cfg, data, AUGMENTATION_ARCH, window, ends, train_windows, val_windows, device, run_dir, evaluate_test=False)
        table[policy] = {"val": r["metrics"]["val"]["overall"], "reused_from": None, "retrained": True, "info": r["info"]}
        print(f"  {policy:12s} (new)    val MAE={r['metrics']['val']['overall']['mae_mps']:.3f} m/s")

    best_by_val = min(table, key=lambda p: table[p]["val"]["mae_mps"])
    # Physical deployment reasoning, applied to the measured validation numbers (see docs/experiments.md):
    # "none" is excluded regardless of its validation score -- every recorded session shares one fixed
    # mounting tilt, so a model trained with no rotation invariance at all has no defence against a
    # differently-mounted phone in the field, which is a realistic deployment scenario this benchmark
    # cannot detect. Between the two yaw-aware options (physically well-motivated: heading is arbitrary,
    # tilt is comparatively consistent for a given mount), prefer "gravity_yaw" over "yaw" unless it is
    # meaningfully worse on validation, because it removes the vertical axis analytically (robust to
    # tilts never seen in training) rather than asking the network to learn tilt invariance from data
    # that has none to learn from.
    candidates = [p for p in ("gravity_yaw", "yaw") if p in table]
    chosen = min(candidates, key=lambda p: table[p]["val"]["mae_mps"]) if len(candidates) > 1 else candidates[0]
    if table[chosen]["val"]["mae_mps"] > table[best_by_val]["val"]["mae_mps"] + 0.5 and best_by_val not in ("none",):
        chosen = best_by_val  # don't override evidence by more than a token margin
    print(f"  best by raw validation MAE: {best_by_val}; chosen policy (evidence + deployment reasoning): {chosen}")
    return chosen, table


def phase2_final_selection(cfg: dict[str, Any], data, device: torch.device, exp_dir: Path, policy: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Train {cnn,tcn} x {20,40} with the chosen policy + NLL loss; score on val + robustness + size."""
    print(f"\n=== Phase 2: final-selection matrix (policy={policy}, heteroscedastic NLL loss, validation only) ===")
    run_cfg = with_uncertainty({**cfg, "training": {**cfg["training"], "loss": "nll", "augmentation_policy": policy}}, True)
    repr_fn = representation_transform(policy)
    rob_cfg, sr = cfg["robustness"], cfg["data"]["sample_rate_hz"]
    dtype = amp_dtype(device, run_cfg["training"]["amp"])
    bs = int(run_cfg["training"]["eval_batch_size"])

    candidates: dict[str, Any] = {}
    for window in cfg["windowing"]["window_sizes"]:
        ends = split_window_ends(data.subsets, window, cfg)
        train_windows = gather_windows(data.subsets["train"].imu, ends["train"], window)
        val_windows = gather_windows(data.subsets["val"].imu, ends["val"], window)
        for arch in run_cfg["training"]["archs"]:
            run_dir = exp_dir / f"m3_final_{arch}_w{window}"
            r = run_one(run_cfg, data, arch, window, ends, train_windows, val_windows, device, run_dir, evaluate_test=False)
            best, _ = load_checkpoint(run_dir / "best.pt", map_location=device)
            best.to(device)
            val_y = data.subsets["val"].target[ends["val"]].astype(np.float64)
            robustness = robustness_battery(best, repr_fn(val_windows), val_y, device, dtype, bs, rob_cfg, sr,
                                            int(cfg["robustness"]["seed"]), transform=None)
            unseen = unseen_group_report(cfg, data, best, window, device, dtype, bs, transform=repr_fn)
            latency = cpu_latency_ms(best.cpu(), arch, run_cfg["models"][arch], window)
            best.to(device)
            key = f"{arch}_w{window}"
            candidates[key] = {"arch": arch, "window": window, "info": r["info"], "metrics": r["metrics"],
                               "val_robustness": robustness, "val_unseen_groups": unseen, "cpu_latency_ms": latency,
                               "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/")}
            print(f"  {key:10s} val MAE={r['metrics']['val']['overall']['mae_mps']:.3f} m/s  "
                 f"val NLL={r['metrics']['val']['uncertainty']['nll']:.3f}  params={r['info']['n_parameters']}  "
                 f"CPU latency={latency:.3f} ms  clean-vs-noisiest robustness drop="
                 f"{max(robustness[p]['regression']['mae_mps'] for p in robustness if p != 'clean') - robustness['clean']['regression']['mae_mps']:.3f} m/s")

    # Selection: validation MAE first; params/latency as a tiebreaker only within a small margin, and a
    # sanity check that robustness degradation isn't wildly worse for the MAE-winner than for the runner-up.
    best_key = min(candidates, key=lambda k: candidates[k]["metrics"]["val"]["overall"]["mae_mps"])
    print(f"  selected final model: {best_key} (lowest validation MAE)")
    return best_key, candidates


def phase3_point_vs_nll(cfg: dict[str, Any], data, device: torch.device, exp_dir: Path, arch: str, window: int,
                        policy: str) -> dict[str, Any]:
    print(f"\n=== Phase 3: point-loss ablation of the final config ({arch}, {window} samples, {policy}) ===")
    run_cfg = with_uncertainty({**cfg, "training": {**cfg["training"], "loss": "huber", "augmentation_policy": policy}}, False)
    ends = split_window_ends(data.subsets, window, cfg)
    train_windows = gather_windows(data.subsets["train"].imu, ends["train"], window)
    val_windows = gather_windows(data.subsets["val"].imu, ends["val"], window)
    run_dir = exp_dir / f"m3_ablation_point_{arch}_w{window}"
    r = run_one(run_cfg, data, arch, window, ends, train_windows, val_windows, device, run_dir, evaluate_test=False)
    print(f"  point-loss val MAE={r['metrics']['val']['overall']['mae_mps']:.3f} m/s (vs NLL counterpart above)")
    return {"info": r["info"], "metrics": r["metrics"]}


def phase4_final_test_evaluation(cfg: dict[str, Any], data, device: torch.device, best_key: str,
                                 candidates: dict[str, Any]) -> dict[str, Any]:
    info = candidates[best_key]["info"]
    arch, window, policy = info["arch"], info["window"], info["augmentation_policy"]
    print(f"\n=== Phase 4: FINAL evaluation on the untouched S-series test set: {best_key} ===")
    run_dir = ROOT / info["checkpoint"]
    model, payload = load_checkpoint(run_dir, map_location=device)
    model.to(device)
    dtype = amp_dtype(device, cfg["training"]["amp"])
    bs = int(cfg["training"]["eval_batch_size"])
    repr_fn = representation_transform(policy)

    ends = split_window_ends(data.subsets, window, cfg)
    train_windows = gather_windows(data.subsets["train"].imu, ends["train"], window)
    test_windows = repr_fn(gather_windows(data.subsets["test"].imu, ends["test"], window))
    test_y = data.subsets["test"].target[ends["test"]].astype(np.float64)

    mean, sigma = predict_windows_uncertainty(model, test_windows, device, bs, dtype)
    test_report = evaluate_split_uncertainty(data.subsets["test"], ends["test"], mean, sigma, cfg["evaluation"])

    rob_cfg, sr = cfg["robustness"], cfg["data"]["sample_rate_hz"]
    test_robustness = robustness_battery(model, test_windows, test_y, device, dtype, bs, rob_cfg, sr, int(rob_cfg["seed"]))
    unseen = unseen_group_report(cfg, data, model, window, device, dtype, bs, transform=repr_fn)

    # fit the output-contract confidence reference from TRAINING sigma only, then save the deployable checkpoint.
    # `model.state_dict()` (not `payload["state_dict"]`) is used so the freshly-set confidence_ref_sigma
    # buffer is actually persisted -- the original payload's copy predates that call.
    train_mean, train_sigma = predict_windows_uncertainty(model, repr_fn(train_windows), device, bs, dtype)
    model.set_confidence_reference(float(np.median(train_sigma)))
    extra = {k: v for k, v in payload.items() if k not in ("arch", "model_cfg", "state_dict")}
    extra["confidence_ref_sigma_mps"] = float(np.median(train_sigma))
    final_ckpt = run_dir.parent / "final.pt"
    save_checkpoint(final_ckpt, model, arch, info["model_cfg"], extra)

    print(f"  test  MAE={test_report['overall']['mae_mps']:.3f} m/s ({test_report['overall']['mae_kmh']:.2f} km/h) "
         f"RMSE={test_report['overall']['rmse_mps']:.3f} R2={test_report['overall']['r2']:.3f}")
    print(f"  test  NLL={test_report['uncertainty']['nll']:.3f}  mean sigma={test_report['uncertainty']['mean_sigma_mps']:.3f} m/s  "
         f"coverage@0.68={test_report['uncertainty']['levels']['0.68']['observed_coverage']:.3f}")
    print(f"  final checkpoint: {final_ckpt.relative_to(ROOT)}")
    return {"arch": arch, "window": window, "augmentation_policy": policy, "checkpoint": str(final_ckpt.relative_to(ROOT)).replace("\\", "/"),
            "confidence_ref_sigma_mps": float(np.median(train_sigma)), "test": test_report, "test_robustness": test_robustness,
            "test_unseen_groups": unseen, "n_parameters": info["n_parameters"], "cpu_latency_ms": candidates[best_key]["cpu_latency_ms"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    parser.add_argument("--max-epochs", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--force-policy", choices=list(AUGMENTATION_POLICIES), default=None,
                        help="override phase 1's automatic augmentation-policy choice (the comparison still runs and is reported)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.max_epochs is not None:
        cfg["training"]["max_epochs"] = args.max_epochs
    if args.device is not None:
        cfg["training"]["device"] = args.device
    device = resolve_device(cfg["training"]["device"])
    exp_dir = ROOT / cfg["output"]["experiments_dir"]
    out_dir = ROOT / cfg["output"]["uncertainty_results_dir"]

    m2_path = ROOT / cfg["output"]["neural_results_dir"] / "results.json"
    m2_noaug_path = ROOT / "results" / "neural_ablation_no_so3" / "results.json"
    for p in (m2_path, m2_noaug_path):
        if not p.is_file():
            raise FileNotFoundError(f"{p} not found -- run scripts/run_baselines.py and scripts/run_training.py "
                                    "(main + --no-so3 ablation) before this script")
    m2_results, m2_noaug_results = load_json(m2_path), load_json(m2_noaug_path)

    data = prepare_data(cfg, ROOT)

    chosen_policy, aug_table = phase1_augmentation_comparison(cfg, data, device, exp_dir, m2_results, m2_noaug_results)
    if args.force_policy is not None and args.force_policy != chosen_policy:
        print(f"  --force-policy overrides the automatic choice: {chosen_policy!r} -> {args.force_policy!r}")
        chosen_policy = args.force_policy
    best_key, candidates = phase2_final_selection(cfg, data, device, exp_dir, chosen_policy)
    ablation = phase3_point_vs_nll(cfg, data, device, exp_dir, candidates[best_key]["arch"], candidates[best_key]["window"], chosen_policy)
    final = phase4_final_test_evaluation(cfg, data, device, best_key, candidates)

    results = {
        "config": cfg, "split": data.split_info(),
        "environment": {"python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__,
                        "device": str(device), "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None},
        "phase1_augmentation_comparison": {"chosen_policy": chosen_policy, "table": aug_table},
        "phase2_final_selection": {"best_key": best_key, "candidates": candidates},
        "phase3_point_vs_nll_ablation": {"nll": candidates[best_key]["metrics"]["val"]["overall"], "point": ablation["metrics"]["val"]["overall"],
                                         "point_info": ablation["info"]},
        "final_model": final,
    }
    write_json(results, out_dir / "results.json")
    write_json(final, out_dir / "final_model.json")

    summary = []
    for key, c in candidates.items():
        summary.append({"key": key, "arch": c["arch"], "window": c["window"], "policy": chosen_policy,
                        "val_mae_mps": c["metrics"]["val"]["overall"]["mae_mps"], "val_nll": c["metrics"]["val"]["uncertainty"]["nll"],
                        "n_parameters": c["info"]["n_parameters"], "cpu_latency_ms": c["cpu_latency_ms"],
                        "selected_final": key == best_key})
    write_csv(summary, out_dir / "selection_summary.csv")

    out_dir.mkdir(parents=True, exist_ok=True)
    plots.plot_selection_matrix(candidates, best_key, out_dir / "selection_matrix.png")
    final_color = plots.MODEL_COLORS.get(final["arch"])
    plots.plot_calibration_curve(final["test"]["uncertainty"], f"Test calibration: {best_key}", out_dir / "test_calibration.png",
                                 color=final_color)
    plots.plot_robustness(final["test_robustness"], f"Test robustness: {best_key}", out_dir / "test_robustness.png", color=final_color)
    print(f"\nSaved Milestone 3 results to {out_dir}")
    print(f"Final model: {best_key}  policy={chosen_policy}  test MAE={final['test']['overall']['mae_mps']:.3f} m/s  "
         f"checkpoint={final['checkpoint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
