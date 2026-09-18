"""Turns a freshly-trained window=20 ``best.pt`` (from ``run_training.py --windows 20
--uncertainty --augmentation yaw --tag production ...``) into a deployable ``final.pt``: fits
``confidence_ref_sigma`` from TRAINING sigma only, exactly mirroring
``scripts/run_uncertainty.py``'s ``phase4_final_test_evaluation``, scoped to just the one production
checkpoint instead of retraining the whole milestone-3 matrix. Writes
``results/uncertainty/final_model_production.json``, the production counterpart to
``results/uncertainty/final_model.json``. See ``docs/production_100hz.md``.

Usage: ``python scripts/finalize_production_checkpoint.py [--arch cnn_mag] [--exp-dir experiments/production_cnn_mag_w20]``
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.augmentation import representation_transform
from src.data.pipeline import load_config, prepare_data, split_window_ends, write_json
from src.data.windowing import gather_windows
from src.training.train import amp_dtype, load_checkpoint, predict_windows_uncertainty, resolve_device, save_checkpoint

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--arch", default="cnn_mag")
parser.add_argument("--exp-dir", default=str(ROOT / "experiments" / "production_cnn_mag_w20"))
parser.add_argument("--augmentation-policy", default="yaw")
args = parser.parse_args()

cfg = load_config(ROOT / "configs" / "member1.yaml")
device = resolve_device(cfg["training"]["device"])
exp_dir = Path(args.exp_dir)
if not exp_dir.is_absolute():
    exp_dir = ROOT / exp_dir
best_ckpt = exp_dir / "best.pt"
model, payload = load_checkpoint(best_ckpt, map_location=device)
model.to(device)
dtype = amp_dtype(device, cfg["training"]["amp"])
bs = int(cfg["training"]["eval_batch_size"])
repr_fn = representation_transform(args.augmentation_policy)

data = prepare_data(cfg, ROOT, verbose=False)
ends = split_window_ends(data.subsets, 20, cfg)
train_windows = repr_fn(gather_windows(data.subsets["train"].imu, ends["train"], 20))

_, train_sigma = predict_windows_uncertainty(model, train_windows, device, bs, dtype)
ref_sigma = float(np.median(train_sigma))
model.set_confidence_reference(ref_sigma)

extra = {k: v for k, v in payload.items() if k not in ("arch", "model_cfg", "state_dict")}
extra["confidence_ref_sigma_mps"] = ref_sigma
final_ckpt = exp_dir / "final.pt"
save_checkpoint(final_ckpt, model, args.arch, payload["model_cfg"], extra)

info = {"arch": args.arch, "window": 20, "augmentation_policy": args.augmentation_policy,
        "checkpoint": str(final_ckpt.relative_to(ROOT)).replace("\\", "/"),
        "confidence_ref_sigma_mps": ref_sigma}
write_json(info, ROOT / "results" / "uncertainty" / "final_model_production.json")
print(json.dumps(info, indent=2))
print(f"Saved deployable checkpoint: {final_ckpt}")
