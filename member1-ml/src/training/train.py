"""Training, prediction and checkpointing for the causal CNN/TCN speed models.

Data contract: training windows are ``float32 [N, T, 6]`` numpy arrays built by
``src.data.windowing`` from IMU rows only; labels are speeds in m/s at the window end.
Validation data is used only for per-epoch monitoring, early stopping and best-checkpoint
selection - never for normalisation or augmentation.
"""
from __future__ import annotations

import math
import os
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import torch

from src.data.windowing import iter_window_chunks
from src.evaluation.metrics import nll_gaussian, regression_metrics
from src.models.tcn_velocity import VelocityNet, build_model, log_var_to_sigma
from src.training.losses import make_loss, make_uncertainty_loss

AugmentFn = Callable[[np.ndarray, np.random.Generator], np.ndarray]


def seed_everything(seed: int, deterministic: bool = True) -> None:
    """Seed Python, NumPy and PyTorch; optionally force deterministic kernels."""
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # required for deterministic cuBLAS
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = deterministic
    torch.use_deterministic_algorithms(deterministic)


def resolve_device(name: str = "auto") -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def amp_dtype(device: torch.device, setting: str | bool = "auto") -> torch.dtype | None:
    """Mixed precision only on CUDA with bfloat16 support (no loss scaling needed); otherwise full precision."""
    if setting in (False, "off") or device.type != "cuda":
        return None
    if setting in (True, "auto", "bf16") and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return None


@torch.no_grad()
def predict_windows(model: VelocityNet, windows: np.ndarray | torch.Tensor, device: torch.device,
                    batch_size: int = 4096, dtype: torch.dtype | None = None) -> np.ndarray:
    """Eval-mode speed predictions (m/s, clipped to >= 0) for ``[N, T, 6]`` windows."""
    model.eval()
    x_all = torch.as_tensor(windows)
    out = []
    for s in range(0, len(x_all), batch_size):
        x = x_all[s:s + batch_size].to(device, non_blocking=True)
        with torch.autocast(device.type, dtype=dtype, enabled=dtype is not None):
            out.append(model(x).float().cpu())
    return torch.clamp(torch.cat(out), min=0.0).numpy().astype(np.float64) if out else np.empty(0)


def predict_indexed(model: VelocityNet, imu: np.ndarray, ends: np.ndarray, window: int, device: torch.device,
                    batch_size: int = 4096, dtype: torch.dtype | None = None, chunk_size: int = 100_000,
                    transform: Callable[[np.ndarray], np.ndarray] | None = None) -> np.ndarray:
    """Like :func:`predict_windows` for windows given by end indices, materialised chunk by chunk.

    ``transform``, if given, is applied to each gathered ``[b, T, 6]`` chunk before prediction (e.g.
    the deterministic gravity-alignment representation from ``src.data.augmentation`` -- see
    :func:`src.data.augmentation.representation_transform`).
    """
    parts = []
    for w in iter_window_chunks(imu, ends, window, chunk_size):
        if transform is not None:
            w = transform(w)
        parts.append(predict_windows(model, w, device, batch_size, dtype))
    return np.concatenate(parts) if parts else np.empty(0)


@torch.no_grad()
def predict_windows_uncertainty(model: VelocityNet, windows: np.ndarray | torch.Tensor, device: torch.device,
                                batch_size: int = 4096, dtype: torch.dtype | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Like :func:`predict_windows` but also returns the predictive std (sigma, m/s, > 0).

    Requires a model built with ``uncertainty=True``. The mean is clipped to ``>= 0`` exactly as in
    :func:`predict_windows`; sigma is never clipped (it is already guaranteed positive and finite
    by the model's clamped log-variance parameterization).
    """
    if not model.uncertainty:
        raise ValueError("model was not built with uncertainty=True; use predict_windows instead")
    model.eval()
    x_all = torch.as_tensor(windows)
    means, sigmas = [], []
    for s in range(0, len(x_all), batch_size):
        x = x_all[s:s + batch_size].to(device, non_blocking=True)
        with torch.autocast(device.type, dtype=dtype, enabled=dtype is not None):
            mean, log_var = model.forward_full(x)
        means.append(mean.float().cpu())
        sigmas.append(log_var_to_sigma(log_var.float()).cpu())
    if not means:
        return np.empty(0), np.empty(0)
    mean = torch.clamp(torch.cat(means), min=0.0).numpy().astype(np.float64)
    sigma = torch.cat(sigmas).numpy().astype(np.float64)
    return mean, sigma


def predict_indexed_uncertainty(model: VelocityNet, imu: np.ndarray, ends: np.ndarray, window: int, device: torch.device,
                                batch_size: int = 4096, dtype: torch.dtype | None = None, chunk_size: int = 100_000,
                                transform: Callable[[np.ndarray], np.ndarray] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Like :func:`predict_windows_uncertainty` for windows given by end indices, chunk by chunk."""
    means, sigmas = [], []
    for w in iter_window_chunks(imu, ends, window, chunk_size):
        if transform is not None:
            w = transform(w)
        m, s = predict_windows_uncertainty(model, w, device, batch_size, dtype)
        means.append(m)
        sigmas.append(s)
    if not means:
        return np.empty(0), np.empty(0)
    return np.concatenate(means), np.concatenate(sigmas)


def save_checkpoint(path: str | Path, model: VelocityNet, arch: str, model_cfg: dict[str, Any],
                    extra: dict[str, Any] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"arch": arch, "model_cfg": model_cfg, "state_dict": model.state_dict(), **(extra or {})}, path)


def load_checkpoint(path: str | Path, map_location: str | torch.device = "cpu") -> tuple[VelocityNet, dict[str, Any]]:
    """Rebuild the model (including its fitted normalisation buffers) from a checkpoint."""
    payload = torch.load(path, map_location=map_location, weights_only=True)
    model = build_model(payload["arch"], payload["model_cfg"])
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, payload


def _lr_lambda(total_steps: int, warmup_steps: int, min_lr_ratio: float) -> Callable[[int], float]:
    def f(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / warmup_steps
        progress = min(1.0, (step - warmup_steps) / max(1, total_steps - warmup_steps))
        return min_lr_ratio + (1 - min_lr_ratio) * 0.5 * (1 + math.cos(math.pi * progress))
    return f


def train_model(
    model: VelocityNet,
    arch: str,
    model_cfg: dict[str, Any],
    train_windows: np.ndarray,
    train_y: np.ndarray,
    val_windows: np.ndarray,
    val_y: np.ndarray,
    tcfg: dict[str, Any],
    augment_fn: AugmentFn | None,
    seed: int,
    device: torch.device,
    checkpoint_path: str | Path,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Train with AdamW + warmup/cosine LR, validate every epoch, early-stop on validation MAE.

    The best (lowest validation MAE) weights are written to ``checkpoint_path``. Returns the
    per-epoch history. ``augment_fn(windows, rng) -> windows'`` is called once per epoch on the
    whole training set (e.g. from ``src.data.augmentation.build_augmentation``); ``None`` disables
    augmentation. Model selection and early stopping always use validation MAE, for both point and
    uncertainty models, so the two are comparable on equal footing.

    ``tcfg["loss"]`` may be ``"huber"``/``"mse"``/``"l1"`` (point) or ``"nll"`` (heteroscedastic
    Gaussian NLL, which requires ``model.uncertainty``). For ``"nll"``, the first
    ``tcfg.get("nll_warmup_epochs", 0)`` epochs instead train the mean head alone with
    ``tcfg.get("warmup_loss", "huber")`` -- a short point-loss warmup before the variance head
    starts receiving gradient, which stabilises early heteroscedastic training.
    """
    if train_windows.ndim != 3 or train_windows.shape[-1] != 6:
        raise ValueError(f"train windows must be [N, T, 6], got {train_windows.shape}")
    use_nll = tcfg["loss"] == "nll"
    if use_nll and not model.uncertainty:
        raise ValueError("loss 'nll' requires a model built with uncertainty=True")
    model.to(device)
    dtype = amp_dtype(device, tcfg.get("amp", "auto"))
    warmup_epochs = int(tcfg.get("nll_warmup_epochs", 0)) if use_nll else 0
    point_loss_fn = make_loss(tcfg.get("warmup_loss", "huber") if use_nll else tcfg["loss"], tcfg.get("huber_delta_mps", 1.0))
    nll_loss_fn = make_uncertainty_loss("nll") if use_nll else None
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(tcfg["lr"]), weight_decay=float(tcfg["weight_decay"]))
    bs, max_epochs = int(tcfg["batch_size"]), int(tcfg["max_epochs"])
    n = len(train_windows)
    steps_per_epoch = math.ceil(n / bs)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, _lr_lambda(
        max_epochs * steps_per_epoch, int(tcfg["warmup_epochs"]) * steps_per_epoch, float(tcfg["min_lr_ratio"])))
    y_train = torch.as_tensor(train_y, dtype=torch.float32, device=device)
    val_x = torch.as_tensor(val_windows)
    generator = torch.Generator().manual_seed(seed)

    history: list[dict[str, Any]] = []
    best_mae, bad_epochs = float("inf"), 0
    for epoch in range(1, max_epochs + 1):
        t0 = time.time()
        model.train()
        in_warmup = use_nll and epoch <= warmup_epochs
        x_np = train_windows if augment_fn is None else augment_fn(train_windows, np.random.default_rng([seed, epoch]))
        x_train = torch.as_tensor(x_np, dtype=torch.float32).to(device)
        perm = torch.randperm(n, generator=generator).to(device)
        loss_sum = torch.zeros((), device=device)
        for s in range(0, n, bs):
            idx = perm[s:s + bs]
            with torch.autocast(device.type, dtype=dtype, enabled=dtype is not None):
                mean, log_var = model.forward_full(x_train[idx])
            if use_nll and not in_warmup:
                loss = nll_loss_fn(mean.float(), log_var.float(), y_train[idx])
            else:
                loss = point_loss_fn(mean.float(), y_train[idx])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(tcfg["grad_clip_norm"]))
            optimizer.step()
            scheduler.step()
            loss_sum += loss.detach() * len(idx)
        train_loss = float(loss_sum) / n
        if not math.isfinite(train_loss):
            raise FloatingPointError(f"non-finite training loss at epoch {epoch}")

        if model.uncertainty:
            val_mean, val_sigma = predict_windows_uncertainty(model, val_x, device, int(tcfg["eval_batch_size"]), dtype)
        else:
            val_mean, val_sigma = predict_windows(model, val_x, device, int(tcfg["eval_batch_size"]), dtype), None
        vm = regression_metrics(val_y, val_mean)
        improved = vm["mae_mps"] < best_mae - float(tcfg["min_delta_mps"])
        extra = {"epoch": epoch, "val_metrics": vm, "seed": seed}
        row = {"epoch": epoch, "lr": optimizer.param_groups[0]["lr"], "train_loss": train_loss, "in_warmup": in_warmup,
               "val_mae_mps": vm["mae_mps"], "val_rmse_mps": vm["rmse_mps"], "val_r2": vm["r2"],
               "best": improved, "epoch_time_s": time.time() - t0}
        if val_sigma is not None:
            row["val_nll"] = nll_gaussian(val_y, val_mean, val_sigma)
            row["val_mean_sigma_mps"] = float(np.mean(val_sigma))
            extra["val_nll"] = row["val_nll"]
        if improved:
            best_mae, bad_epochs = vm["mae_mps"], 0
            save_checkpoint(checkpoint_path, model, arch, model_cfg, extra)
        else:
            bad_epochs += 1
        history.append(row)
        nll_part = f" val NLL={row['val_nll']:.3f} sigma~{row['val_mean_sigma_mps']:.2f}" if val_sigma is not None else ""
        log(f"    epoch {epoch:3d} lr={row['lr']:.2e} train_loss={train_loss:.4f}{' [warmup]' if in_warmup else ''} "
            f"val MAE={vm['mae_mps']:.3f} RMSE={vm['rmse_mps']:.3f} R2={vm['r2']:.3f}{nll_part}"
            f"{' *' if improved else ''} ({row['epoch_time_s']:.1f}s)")
        if bad_epochs >= int(tcfg["early_stopping_patience"]):
            log(f"    early stopping at epoch {epoch} (best val MAE {best_mae:.3f})")
            break
    return history
