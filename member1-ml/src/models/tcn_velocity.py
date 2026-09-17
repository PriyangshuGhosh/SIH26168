"""Lightweight causal temporal models for IMU-only vehicle speed estimation.

Both models take ``[B, T, 6]`` float32 IMU windows (``[acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z]``,
raw physical units) and return ``[B]`` speed in m/s at the last time step of the window.

* ``cnn``: residual blocks of non-dilated causal convolutions, then global average pooling over
  the window. Every sample in the window is at or before the prediction point, so pooling is causal
  with respect to the prediction.
* ``tcn``: residual blocks of dilated causal convolutions whose receptive field covers the whole
  window; the prediction is read from the feature vector at the last time step.

Causality: convolutions are left-padded only, so the feature at step ``t`` depends on inputs
``<= t``. BatchNorm is used (not Group/LayerNorm over time) because in eval mode it is a per-step
affine map, so the causal property holds exactly at inference and it fuses into convs for export.

Normalisation is part of the model (buffers, fitted on training data only):
* input: one scale per sensor (the RMS of the three acc axes, and of the three gyr axes). No
  per-axis mean is subtracted, because per-axis statistics depend on phone orientation and would
  conflict with SO(3) rotation augmentation; a shared per-sensor scale keeps rotations exact.
* output: ``speed = target_mean + target_std * head(...)``.
Predictions are not clipped inside the model; :func:`src.training.train.predict` clips to ``>= 0``.

Uncertainty (Milestone 3, opt-in via ``uncertainty=True`` / ``model_cfg["uncertainty"]``): a second
linear head predicts a *raw* (standardized) log-variance from the same pooled features as the mean
head. It is clamped to ``[log_var_min, log_var_max]`` before any ``exp()`` is taken, which is what
makes the parameterization numerically stable -- ``exp()`` of a bounded input can never overflow or
underflow to zero, so the predictive variance is always finite and strictly positive by
construction, for any input, at any point in training. The clamped raw value is converted to a
native-units log-variance via ``log_var_mps2 = 2*log(target_std) + raw_log_var``, i.e. the
predictive variance is expressed as a multiple of the training-target variance (so a freshly
initialised head, whose weights are zeroed, starts by predicting the dataset's marginal variance --
a reasonable prior before any input-dependent signal is learned). See
:func:`src.training.losses.heteroscedastic_gaussian_nll` for the loss that trains this head, and
:meth:`VelocityNet.confidence_from_sigma` for the uncertainty -> confidence mapping used in the
Member 3 output contract (``docs/member1_output_contract.md``).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

N_CHANNELS = 6


class CausalConv1d(nn.Module):
    """Conv1d with left-only padding: output length == input length, no lookahead."""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, dilation: int = 1):
        super().__init__()
        self.left_pad = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(in_ch, out_ch, kernel_size, dilation=dilation, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(F.pad(x, (self.left_pad, 0)))


class ResidualBlock(nn.Module):
    """(causal conv -> BN -> ReLU -> dropout) x 2 with a residual connection."""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, dilation: int, dropout: float):
        super().__init__()
        self.net = nn.Sequential(
            CausalConv1d(in_ch, out_ch, kernel_size, dilation), nn.BatchNorm1d(out_ch), nn.ReLU(), nn.Dropout(dropout),
            CausalConv1d(out_ch, out_ch, kernel_size, dilation), nn.BatchNorm1d(out_ch),
        )
        self.skip = nn.Identity() if in_ch == out_ch else nn.Sequential(nn.Conv1d(in_ch, out_ch, 1, bias=False),
                                                                         nn.BatchNorm1d(out_ch))
        self.out = nn.Sequential(nn.ReLU(), nn.Dropout(dropout))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.out(self.net(x) + self.skip(x))


class VelocityNet(nn.Module):
    """Causal CNN/TCN speed regressor, with an optional heteroscedastic uncertainty head.

    Build via :func:`build_model`. ``forward(x)`` always returns just the mean (m/s), for drop-in
    use by every point-estimate predictor and test already written against it; use
    :meth:`forward_full` to also get the predictive variance from an uncertainty-enabled model.
    """

    def __init__(self, arch: str, channels: int, kernel_size: int, dilations: list[int], dropout: float,
                uncertainty: bool = False, log_var_min: float = -6.0, log_var_max: float = 6.0):
        super().__init__()
        if arch not in ("cnn", "tcn"):
            raise ValueError(f"unknown arch {arch!r}")
        if uncertainty and log_var_min >= log_var_max:
            raise ValueError(f"log_var_min ({log_var_min}) must be < log_var_max ({log_var_max})")
        self.arch = arch
        self.uncertainty = bool(uncertainty)
        self.log_var_min, self.log_var_max = float(log_var_min), float(log_var_max)
        blocks, in_ch = [], N_CHANNELS
        for d in dilations:
            blocks.append(ResidualBlock(in_ch, channels, kernel_size, d, dropout))
            in_ch = channels
        self.blocks = nn.Sequential(*blocks)
        self.head = nn.Linear(channels, 1)
        if self.uncertainty:
            self.log_var_head = nn.Linear(channels, 1)
            # zero-init: a freshly built model predicts raw_log_var == 0, i.e. variance ==
            # target_std**2 (the dataset's marginal variance), a sane prior before any
            # input-dependent uncertainty signal is learned.
            nn.init.zeros_(self.log_var_head.weight)
            nn.init.zeros_(self.log_var_head.bias)
        self.receptive_field = 1 + 2 * (kernel_size - 1) * sum(dilations)
        self.register_buffer("input_scale", torch.ones(N_CHANNELS))
        self.register_buffer("target_mean", torch.zeros(()))
        self.register_buffer("target_std", torch.ones(()))
        self.register_buffer("confidence_ref_sigma", torch.ones(()))

    def set_normalization(self, input_scale: np.ndarray, target_mean: float, target_std: float) -> None:
        if not (np.isfinite(target_std) and target_std > 0):
            raise ValueError(f"target_std must be finite and > 0, got {target_std}")
        self.input_scale.copy_(torch.as_tensor(input_scale, dtype=torch.float32))
        self.target_mean.fill_(float(target_mean))
        self.target_std.fill_(float(target_std))

    def set_confidence_reference(self, ref_sigma_mps: float) -> None:
        """Fit the uncertainty -> confidence reference scale (e.g. the median predicted sigma on
        training data), stored as a checkpoint buffer so inference needs no extra config."""
        if not (np.isfinite(ref_sigma_mps) and ref_sigma_mps > 0):
            raise ValueError(f"ref_sigma_mps must be finite and > 0, got {ref_sigma_mps}")
        self.confidence_ref_sigma.fill_(float(ref_sigma_mps))

    def confidence_from_sigma(self, sigma: torch.Tensor) -> torch.Tensor:
        """Map predictive std (m/s, >= 0) to confidence in ``(0, 1]``, monotonically decreasing.

        ``confidence = 1 / (1 + sigma / confidence_ref_sigma)``: 1 at ``sigma == 0``, 0.5 at
        ``sigma == confidence_ref_sigma``, and asymptotically 0 as sigma grows. This is a simple,
        bounded, order-preserving summary of the same information already in ``uncertainty`` --
        Member 3 is free to use either field; ``uncertainty`` (m/s) is the one with physical units.
        """
        return 1.0 / (1.0 + sigma / self.confidence_ref_sigma)

    def features(self, x: torch.Tensor) -> torch.Tensor:
        """``[B, T, 6]`` -> per-step causal features ``[B, C, T]``."""
        if x.ndim != 3 or x.shape[-1] != N_CHANNELS:
            raise ValueError(f"expected [B, T, {N_CHANNELS}], got {tuple(x.shape)}")
        return self.blocks((x / self.input_scale).transpose(1, 2))

    def forward_full(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor | None]:
        """``(mean_mps [B], log_var_mps2 [B] or None)``. ``log_var_mps2`` is ``None`` unless this
        model was built with ``uncertainty=True``; when present it is already clamped (see class
        docstring), so ``exp()`` of it, or of its negation, is always finite and positive."""
        h = self.features(x)
        pooled = h.mean(dim=2) if self.arch == "cnn" else h[:, :, -1]
        mean = self.target_mean + self.target_std * self.head(pooled).squeeze(-1)
        if not self.uncertainty:
            return mean, None
        raw_log_var = torch.clamp(self.log_var_head(pooled).squeeze(-1), self.log_var_min, self.log_var_max)
        log_var_mps2 = 2.0 * torch.log(self.target_std) + raw_log_var
        return mean, log_var_mps2

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.forward_full(x)[0]


def build_model(arch: str, model_cfg: dict[str, Any]) -> VelocityNet:
    """Build from the ``models.<arch>`` config section. ``uncertainty`` defaults to ``False`` (the
    Milestone 2 point-estimate behaviour) so existing configs and checkpoints are unaffected."""
    if arch == "cnn":
        dilations = [1] * int(model_cfg["n_blocks"])
    elif arch == "tcn":
        dilations = [int(d) for d in model_cfg["dilations"]]
    else:
        raise ValueError(f"unknown arch {arch!r}")
    return VelocityNet(arch, int(model_cfg["channels"]), int(model_cfg["kernel_size"]), dilations, float(model_cfg["dropout"]),
                       bool(model_cfg.get("uncertainty", False)), float(model_cfg.get("log_var_min", -6.0)),
                       float(model_cfg.get("log_var_max", 6.0)))


def log_var_to_sigma(log_var_mps2: torch.Tensor) -> torch.Tensor:
    """Native-units log-variance -> predictive standard deviation (m/s)."""
    return torch.exp(0.5 * log_var_mps2)


def fit_normalization(train_imu: np.ndarray, train_targets: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Fit input scale (per sensor RMS) and target mean/std on TRAINING data only."""
    acc_rms = float(np.sqrt(np.mean(np.square(train_imu[:, 0:3], dtype=np.float64))))
    gyr_rms = float(np.sqrt(np.mean(np.square(train_imu[:, 3:6], dtype=np.float64))))
    scale = np.array([acc_rms] * 3 + [gyr_rms] * 3, dtype=np.float32)
    if not np.all(np.isfinite(scale)) or np.any(scale <= 0):
        raise ValueError(f"invalid input scale {scale}")
    return scale, float(np.mean(train_targets)), float(np.std(train_targets))


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
