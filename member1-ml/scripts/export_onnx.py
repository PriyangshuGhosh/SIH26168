"""Milestone 4: export the FINAL Member 1 checkpoint to ONNX and verify it.

Usage:
    python scripts/export_onnx.py [--config configs/member1.yaml]
                                  [--final-model-json results/uncertainty/final_model.json]
                                  [--checkpoint PATH --window N [--augmentation-policy yaw]]
                                  [--out PATH] [--opset 17] [--atol 1e-4 --rtol 1e-3]

By default this resolves the checkpoint, window and augmentation policy from
``results/uncertainty/final_model.json`` (written by ``scripts/run_uncertainty.py``, phase 4) --
the same checkpoint documented in ``docs/experiments.md`` and ``docs/member1_output_contract.md``.
Pass ``--checkpoint``/``--window`` to export a different (already-trained) checkpoint instead; this
script never trains or retrains anything.

Verification, all against the SAME exported ONNX file:
  1. output shapes and finiteness at several batch sizes (dynamic-batch support);
  2. value-range sanity (velocity >= 0; for an uncertainty model, sigma > 0 and 0 < confidence <= 1);
  3. PyTorch vs ONNX Runtime numerical agreement, on real validation-split windows (never test --
     the S-series test set was already touched exactly once, in Milestone 3's final evaluation, and
     this script does not need it to verify an export) plus a synthetic random batch;
  4. a plain CPU ONNX Runtime inference run.

Writes ``<out>.json`` (the verification + benchmark report) next to the ``.onnx`` file, using
``src.inference.benchmark.benchmark_report`` for CPU latency/size/parameter-count numbers.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.augmentation import representation_transform  # noqa: E402
from src.data.pipeline import load_config, prepare_data, split_window_ends, write_json  # noqa: E402
from src.data.windowing import gather_windows  # noqa: E402
from src.inference.benchmark import benchmark_report  # noqa: E402
from src.inference.export_onnx import (  # noqa: E402
    compare_pytorch_onnx, export_model, load_onnx_session, run_onnx, verify_shapes_and_finite,
)
from src.training.train import load_checkpoint  # noqa: E402


def resolve_checkpoint(args) -> tuple[Path, int, str]:
    if args.checkpoint is not None:
        if args.window is None:
            raise SystemExit("--window is required when --checkpoint is given directly")
        return Path(args.checkpoint), args.window, args.augmentation_policy or "yaw"
    info = json.loads(Path(args.final_model_json).read_text(encoding="utf-8"))
    return ROOT / info["checkpoint"], int(info["window"]), info["augmentation_policy"]


def value_range_checks(out: dict[str, np.ndarray], uncertainty: bool) -> dict[str, bool]:
    checks = {"velocity_nonnegative": bool(np.all(out["velocity_mps"] >= 0.0))}
    if uncertainty:
        checks["sigma_positive"] = bool(np.all(out["uncertainty"] > 0.0))
        checks["confidence_in_0_1"] = bool(np.all((out["confidence"] > 0.0) & (out["confidence"] <= 1.0)))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    parser.add_argument("--final-model-json", default=str(ROOT / "results" / "uncertainty" / "final_model.json"))
    parser.add_argument("--checkpoint", default=None, help="export this .pt directly instead of final_model.json's entry")
    parser.add_argument("--window", type=int, default=None, help="required with --checkpoint")
    parser.add_argument("--augmentation-policy", default=None, help="representation policy for --checkpoint (default: yaw)")
    parser.add_argument("--out", default=None, help="ONNX output path (default: alongside the checkpoint, same stem + .onnx)")
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--n-samples", type=int, default=512, help="number of real validation windows used for the PyTorch/ONNX agreement check")
    parser.add_argument("--atol", type=float, default=1e-4)
    parser.add_argument("--rtol", type=float, default=1e-3)
    args = parser.parse_args()

    cfg = load_config(args.config)
    ckpt_path, window, policy = resolve_checkpoint(args)
    print(f"Checkpoint: {ckpt_path}  window={window} ({window / cfg['data']['sample_rate_hz']:g} s)  policy={policy!r}")

    model, payload = load_checkpoint(ckpt_path, map_location="cpu")
    model.eval()
    print(f"  arch={payload['arch']}  uncertainty={model.uncertainty}  n_parameters={sum(p.numel() for p in model.parameters())}")

    out_path = Path(args.out) if args.out else ckpt_path.with_suffix(".onnx")
    onnx_path = export_model(model, window, out_path, opset=args.opset)
    onnx.checker.check_model(str(onnx_path))
    print(f"  exported to {onnx_path} ({onnx_path.stat().st_size / 1024.0:.1f} KB), passed onnx.checker")

    session = load_onnx_session(onnx_path)

    report: dict = {
        "checkpoint": str(ckpt_path.relative_to(ROOT)) if ckpt_path.is_relative_to(ROOT) else str(ckpt_path),
        "onnx_path": str(onnx_path.relative_to(ROOT)) if onnx_path.is_relative_to(ROOT) else str(onnx_path),
        "arch": payload["arch"], "window": window, "augmentation_policy": policy, "uncertainty": model.uncertainty,
        "opset": args.opset,
        "environment": {"python": platform.python_version(), "torch": torch.__version__,
                        "onnx": onnx.__version__, "onnxruntime": onnxruntime.__version__},
    }

    # 1-2: dynamic batch, shapes, finiteness, value ranges (synthetic input; no data needed)
    shapes = verify_shapes_and_finite(session, window, batch_sizes=(1, 8, 64))
    for b, out in shapes.items():
        if not all(v["finite"] for v in out.values()):
            raise RuntimeError(f"non-finite ONNX output at batch size {b}: {out}")
    report["shape_and_finite_check"] = shapes
    rng_x = np.random.default_rng(1).standard_normal((16, window, 6)).astype(np.float32)
    range_report = value_range_checks(run_onnx(session, rng_x), model.uncertainty)
    if not all(range_report.values()):
        raise RuntimeError(f"value-range check failed: {range_report}")
    report["value_range_check"] = range_report
    print(f"  shapes/finite OK at batch sizes {list(shapes)}; value-range checks OK: {range_report}")

    # 3: PyTorch vs ONNX agreement on real validation windows + a random batch
    data = prepare_data(cfg, ROOT, verbose=False)
    ends = split_window_ends(data.subsets, window, cfg)
    val_windows = gather_windows(data.subsets["val"].imu, ends["val"], window)
    repr_fn = representation_transform(policy)
    val_windows = repr_fn(val_windows)
    rng = np.random.default_rng(0)
    idx = rng.choice(len(val_windows), size=min(args.n_samples, len(val_windows)), replace=False)
    real_agreement = compare_pytorch_onnx(model, session, val_windows[idx], atol=args.atol, rtol=args.rtol)
    synth_agreement = compare_pytorch_onnx(model, session, rng_x, atol=args.atol, rtol=args.rtol)
    report["pytorch_vs_onnx"] = {"real_validation_windows": real_agreement, "synthetic_random_windows": synth_agreement}
    for label, agreement in (("real", real_agreement), ("synthetic", synth_agreement)):
        for name, r in agreement.items():
            status = "OK" if r["allclose"] else "MISMATCH"
            print(f"  [{label}] {name}: max_abs_diff={r['max_abs_diff']:.3e} mean_abs_diff={r['mean_abs_diff']:.3e} ({status})")
        if not all(r["allclose"] for r in agreement.values()):
            raise RuntimeError(f"PyTorch vs ONNX agreement failed on {label} windows (tolerance atol={args.atol}, rtol={args.rtol})")

    # 4: benchmark (also exercises a plain CPU ONNX Runtime inference run).
    # Two thread settings are measured and both are reported honestly:
    #  - "default_threading": this dev machine's default torch/ONNX Runtime thread count.
    #  - "single_threaded_edge": num_threads=1 on both sides, closer to a lean embedded deployment
    #    (Member 5's C++20 + ONNX Runtime target) -- for a model this small, multi-threaded dispatch
    #    overhead measurably dominates actual compute time at batch size 1 on this machine (verified:
    #    default-threading PyTorch latency was several times the single-threaded number).
    report["benchmark_default_threading"] = benchmark_report(model, session, onnx_path, window)
    single_session = load_onnx_session(onnx_path, intra_op_num_threads=1, inter_op_num_threads=1)
    report["benchmark_single_threaded_edge"] = benchmark_report(model, single_session, onnx_path, window, num_threads=1)
    bd, bs_ = report["benchmark_default_threading"], report["benchmark_single_threaded_edge"]
    print(f"  n_parameters={bd['n_parameters']}  onnx size={bd['onnx_model_size_kb']:.1f} KB")
    print(f"  [default threading]      PyTorch CPU latency={bd['pytorch_cpu_latency_ms']:.3f} ms  ONNX CPU latency={bd['onnx_cpu_latency_ms']:.3f} ms")
    print(f"  [single-threaded, edge]  PyTorch CPU latency={bs_['pytorch_cpu_latency_ms']:.3f} ms  ONNX CPU latency={bs_['onnx_cpu_latency_ms']:.3f} ms")

    report_path = onnx_path.with_suffix(".onnx_report.json")
    write_json(report, report_path)
    print(f"\nAll ONNX export checks passed. Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
