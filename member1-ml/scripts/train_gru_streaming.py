"""Truncated-BPTT streaming training for the GRU velocity model (``models.gru`` in
configs/member1.yaml). See docs/gru_velocity.md for why this exists and how it differs from
``scripts/run_training.py``.

The existing windowed pipeline (:mod:`src.data.windowing`, reused by ``run_training.py`` for
cnn/tcn/gru) always resets the model's state at the start of every independent 2-second training
window, so a GRU trained that way never sees a gradient signal that rewards remembering anything
*across* window boundaries -- confirmed empirically: a GRU trained with ``run_training.py`` predicts
~0 m/s after a sustained straight-line acceleration, exactly like the stateless CNN/TCN it was meant
to improve on.

This script instead trains on whole, session-contiguous IMU sequences (still respecting the exact
same trip-family train/val/test split -- no group leakage), carrying the GRU's hidden state forward
across truncated chunks *within* a session (reset only at session start, matching the real
discontinuity Member 2 itself resets on), and supervising the loss at **every** 10 Hz row using the
real ``target_speed_mps`` label -- not just window-end points. This is what actually trains
:meth:`VelocityNet.step` to be usable as a genuinely stateful streaming estimator.

Usage:
    python scripts/train_gru_streaming.py [--config configs/member1.yaml] [--max-epochs 20]
        [--chunk-steps 300] [--tag m1_gru_streaming] [--device cpu]
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.augmentation import rotate_windows, yaw_rotation_matrices  # noqa: E402
from src.data.pipeline import load_config, prepare_data, write_json  # noqa: E402
from src.data.windowing import session_starts  # noqa: E402
from src.evaluation.metrics import regression_metrics  # noqa: E402
from src.models.tcn_velocity import build_model, count_parameters, fit_normalization  # noqa: E402
from src.training.train import resolve_device, save_checkpoint, seed_everything  # noqa: E402

_LOG_2PI = math.log(2.0 * math.pi)

# Near-stationary rows (true speed < this) get an upweighted loss -- NOT a hardcoded/clamped
# output, just a standard weighted-regression emphasis so the model is pushed harder, through
# ordinary gradient descent, to get the low-speed regime right. This directly targets the
# stationary-MAE regression seen in the unweighted first streaming run (see docs/gru_velocity.md).
STATIONARY_WEIGHT_THRESHOLD_MPS = 1.0
# 3.0 (first attempt) fixed stationary MAE (11.3 -> 1.2 m/s) but overcorrected: it materially broke
# steady-speed accuracy (4.9 -> 8.5 m/s MAE, streaming eval), the regime this whole investigation
# was about. 1.5 is a single, principled bisection between "no weighting" (steady-speed good,
# stationary bad) and "3x" (stationary good, steady-speed bad) -- not an open-ended hyperparameter
# search. See docs/gru_velocity.md.
STATIONARY_WEIGHT = 1.5


def weighted_huber(pred: torch.Tensor, target: torch.Tensor, weight: torch.Tensor, delta: float = 1.0) -> torch.Tensor:
    per_elem = F.huber_loss(pred, target, delta=delta, reduction="none")
    return (per_elem * weight).sum() / weight.sum()


def weighted_gaussian_nll(mean: torch.Tensor, log_var: torch.Tensor, target: torch.Tensor,
                          weight: torch.Tensor) -> torch.Tensor:
    inv_var = torch.exp(-log_var)
    nll = 0.5 * (log_var + (target - mean) ** 2 * inv_var + _LOG_2PI)
    return (nll * weight).sum() / weight.sum()


def session_ranges(session_id: np.ndarray) -> list[tuple[int, int]]:
    starts = np.flatnonzero(session_starts(session_id))
    ends = np.r_[starts[1:], len(session_id)]
    return list(zip(starts.tolist(), ends.tolist()))


def run_session_tbptt(model, imu: np.ndarray, target: np.ndarray, device: torch.device,
                      chunk_steps: int, use_nll: bool,
                      optimizer=None) -> tuple[float, int]:
    """One pass (train if ``optimizer`` given, else eval) over one session, chunked for TBPTT.
    Returns (summed loss over all rows, n rows)."""
    n = len(target)
    h = torch.zeros(model.gru_layers, 1, model.gru_hidden, device=device)
    total_loss, total_n = 0.0, 0
    training = optimizer is not None
    for s in range(0, n, chunk_steps):
        e = min(s + chunk_steps, n)
        x = torch.as_tensor(imu[s:e], dtype=torch.float32, device=device).unsqueeze(0)  # [1, L, 6]
        y = torch.as_tensor(target[s:e], dtype=torch.float32, device=device)  # [L]
        h_in = h.detach() if training else h
        if model.derive_magnitude_channels:
            acc_mag = x[..., 0:3].norm(dim=-1, keepdim=True)
            gyr_mag = x[..., 3:6].norm(dim=-1, keepdim=True)
            xe = torch.cat([x, acc_mag, gyr_mag], dim=-1)
        else:
            xe = x
        out, h = model.gru(xe / model.input_scale, h_in)  # out: [1, L, H]
        pooled = out[0]  # [L, H]
        # target_speed_mps has NaN at the last row of every session (see docs/data_protocol.md);
        # mask those rows out of the loss rather than letting a NaN poison the whole chunk's gradient.
        finite = torch.isfinite(y)
        if not bool(finite.any()):
            continue
        y_f = y[finite]
        weight = torch.where(y_f < STATIONARY_WEIGHT_THRESHOLD_MPS,
                             torch.full_like(y_f, STATIONARY_WEIGHT), torch.ones_like(y_f))
        mean = model.target_mean + model.target_std * model.head(pooled).squeeze(-1)  # [L]
        if use_nll:
            raw_log_var = torch.clamp(model.log_var_head(pooled).squeeze(-1), model.log_var_min, model.log_var_max)
            log_var = 2.0 * torch.log(model.target_std) + raw_log_var
            loss = weighted_gaussian_nll(mean[finite], log_var[finite], y_f, weight)
        else:
            loss = weighted_huber(mean[finite], y_f, weight)
        if training:
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        n_valid = int(finite.sum())
        total_loss += float(loss.detach()) * n_valid
        total_n += n_valid
        if not training:
            h = h.detach()
    return total_loss, total_n


@torch.no_grad()
def predict_session_streaming(model, imu: np.ndarray, device: torch.device) -> np.ndarray:
    h = torch.zeros(model.gru_layers, 1, model.gru_hidden, device=device)
    x = torch.as_tensor(imu, dtype=torch.float32, device=device).unsqueeze(0)
    if model.derive_magnitude_channels:
        acc_mag = x[..., 0:3].norm(dim=-1, keepdim=True)
        gyr_mag = x[..., 3:6].norm(dim=-1, keepdim=True)
        xe = torch.cat([x, acc_mag, gyr_mag], dim=-1)
    else:
        xe = x
    out, _ = model.gru(xe / model.input_scale, h)
    mean = model.target_mean + model.target_std * model.head(out[0]).squeeze(-1)
    return torch.clamp(mean, min=0.0).cpu().numpy().astype(np.float64)


def _lr_at_epoch(epoch: int, peak_lr: float, warmup_epochs: int, max_epochs: int, min_lr_ratio: float = 0.05) -> float:
    """1-epoch-granularity warmup + cosine decay, mirroring src.training.train._lr_lambda's shape
    but applied per-epoch (TBPTT steps per epoch vary with session shuffling order, so a clean
    per-step schedule isn't as simple here; per-epoch is enough to fix the instability seen with a
    constant LR -- see docs/gru_velocity.md)."""
    if epoch <= warmup_epochs:
        return peak_lr * epoch / max(1, warmup_epochs)
    progress = min(1.0, (epoch - warmup_epochs) / max(1, max_epochs - warmup_epochs))
    return peak_lr * (min_lr_ratio + (1 - min_lr_ratio) * 0.5 * (1 + math.cos(math.pi * progress)))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT / "configs" / "member1.yaml"))
    p.add_argument("--max-epochs", type=int, default=20)
    p.add_argument("--chunk-steps", type=int, default=300)
    p.add_argument("--point-warmup-epochs", type=int, default=8)
    p.add_argument("--lr", type=float, default=1.0e-3)
    p.add_argument("--lr-warmup-epochs", type=int, default=1)
    p.add_argument("--tag", default="m1_gru_streaming")
    p.add_argument("--device", default="cpu")
    p.add_argument("--patience", type=int, default=6)
    args = p.parse_args()

    cfg = load_config(args.config)
    seed_everything(int(cfg["seed"]))
    device = resolve_device(args.device)
    data = prepare_data(cfg, ROOT)
    train_sub, val_sub = data.subsets["train"], data.subsets["val"]

    model_cfg = cfg["models"]["gru"]
    model = build_model("gru", model_cfg)
    finite_target = np.isfinite(train_sub.target)
    model.set_normalization(*fit_normalization(train_sub.imu, train_sub.target[finite_target].astype(np.float64),
                                               derive_magnitude_channels=True))
    model.to(device)
    n_params = count_parameters(model)
    print(f"GRU streaming | {n_params} parameters | uncertainty={model.uncertainty} | device={device}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-2)

    train_ranges = session_ranges(train_sub.session_id)
    val_ranges = session_ranges(val_sub.session_id)
    rng = np.random.default_rng(int(cfg["seed"]))

    run_dir = ROOT / cfg["output"]["experiments_dir"] / f"{args.tag}_gru_w20"
    run_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = run_dir / "best.pt"

    best_val_mae, bad_epochs = float("inf"), 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, args.max_epochs + 1):
        t0 = time.time()
        lr_now = _lr_at_epoch(epoch, args.lr, args.lr_warmup_epochs, args.max_epochs)
        for g in optimizer.param_groups:
            g["lr"] = lr_now
        model.train()
        use_nll = model.uncertainty and epoch > args.point_warmup_epochs
        order = rng.permutation(len(train_ranges))
        train_loss_sum, train_n = 0.0, 0
        for si in order:
            s, e = train_ranges[si]
            imu_sess = train_sub.imu[s:e]
            target_sess = train_sub.target[s:e]
            rot = yaw_rotation_matrices(1, rng, 180.0)
            imu_sess = rotate_windows(imu_sess[None, :, :], rot)[0]
            loss_sum, n = run_session_tbptt(model, imu_sess, target_sess, device, args.chunk_steps,
                                            use_nll, optimizer)
            train_loss_sum += loss_sum
            train_n += n
        train_loss = train_loss_sum / max(train_n, 1)

        model.eval()
        val_preds, val_y = [], []
        for s, e in val_ranges:
            pred = predict_session_streaming(model, val_sub.imu[s:e], device)
            val_preds.append(pred)
            val_y.append(val_sub.target[s:e])
        val_pred = np.concatenate(val_preds)
        val_y_arr = np.concatenate(val_y)
        finite = np.isfinite(val_y_arr)
        val_pred, val_y_arr = val_pred[finite], val_y_arr[finite]
        vm = regression_metrics(val_y_arr, val_pred)
        stat_mask = val_y_arr < STATIONARY_WEIGHT_THRESHOLD_MPS
        stat_mae = float(np.mean(np.abs(val_pred[stat_mask] - val_y_arr[stat_mask]))) if stat_mask.any() else float("nan")
        # Selection score balances overall accuracy against the stationary regime specifically, so
        # a checkpoint that trades stationary accuracy away for a marginally better overall MAE
        # (what happened, unweighted, in the first streaming run) is not selected as "best".
        score = vm["mae_mps"] + 0.5 * (stat_mae if math.isfinite(stat_mae) else 0.0)
        improved = score < best_val_mae - 0.005
        row = {"epoch": epoch, "lr": lr_now, "train_loss": train_loss, "use_nll": use_nll,
               "val_mae_mps": vm["mae_mps"], "val_rmse_mps": vm["rmse_mps"], "val_r2": vm["r2"],
               "val_stationary_mae_mps": stat_mae, "selection_score": score,
               "best": improved, "epoch_time_s": time.time() - t0}
        history.append(row)
        print(f"  epoch {epoch:3d} lr={lr_now:.2e} train_loss={train_loss:.4f}{' [nll]' if use_nll else ' [point]'} "
              f"val MAE={vm['mae_mps']:.3f} RMSE={vm['rmse_mps']:.3f} R2={vm['r2']:.3f} "
              f"stationary_MAE={stat_mae:.3f}{' *' if improved else ''} ({row['epoch_time_s']:.1f}s)")
        if improved:
            best_val_mae, bad_epochs = score, 0
            save_checkpoint(ckpt_path, model, "gru", model_cfg,
                            {"epoch": epoch, "val_metrics": vm, "val_stationary_mae_mps": stat_mae})
        else:
            bad_epochs += 1
        if bad_epochs >= args.patience:
            print(f"  early stopping at epoch {epoch} (best selection score {best_val_mae:.3f})")
            break

    write_json(history, run_dir / "history.json")
    print(f"\nBest streaming GRU: selection score={best_val_mae:.3f}  checkpoint={ckpt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
