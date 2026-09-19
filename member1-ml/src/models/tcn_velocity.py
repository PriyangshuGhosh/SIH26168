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
    """Causal CNN/TCN/GRU speed regressor, with an optional heteroscedastic uncertainty head.

    Build via :func:`build_model`. ``forward(x)`` always returns just the mean (m/s), for drop-in
    use by every point-estimate predictor and test already written against it; use
    :meth:`forward_full` to also get the predictive variance from an uncertainty-enabled model.

    ``arch="gru"`` (added for the long-duration-blackout investigation, see
    ``docs/gru_velocity.md``) replaces the fixed-receptive-field conv blocks with a single-layer
    GRU. Trained exactly like "cnn"/"tcn" -- fixed-length windows, hidden state reset to zero at
    the start of every window -- but because an RNN's hidden state is a first-class tensor (unlike
    a conv stack's fixed window), it can *also* be run in a genuinely stateful, cross-call streaming
    fashion at inference time via :meth:`step`, which a fixed causal-conv receptive field cannot do
    regardless of window length. See :meth:`step` and ``src/inference/gru_streaming.py``.
    """

    def __init__(self, arch: str, channels: int, kernel_size: int, dilations: list[int], dropout: float,
                uncertainty: bool = False, log_var_min: float = -6.0, log_var_max: float = 6.0,
                derive_magnitude_channels: bool = False, gru_layers: int = 1):
        super().__init__()
        if arch not in ("cnn", "tcn", "gru"):
            raise ValueError(f"unknown arch {arch!r}")
        if uncertainty and log_var_min >= log_var_max:
            raise ValueError(f"log_var_min ({log_var_min}) must be < log_var_max ({log_var_max})")
        self.arch = arch
        self.uncertainty = bool(uncertainty)
        self.log_var_min, self.log_var_max = float(log_var_min), float(log_var_max)
        self.derive_magnitude_channels = bool(derive_magnitude_channels)
        # Public input/output contract is always [B, T, N_CHANNELS] (6): |acc|/|gyr| magnitude, when
        # enabled, is derived internally from that same 6-channel input (same timestep only, no
        # lookahead) and only changes the *internal* channel count the conv blocks operate on -- see
        # `features()`. This keeps every external caller (windowing, ONNX graph I/O, the production
        # Member 2 adapter) unchanged regardless of this flag.
        eff_channels = N_CHANNELS + 2 if self.derive_magnitude_channels else N_CHANNELS
        if arch == "gru":
            self.gru_layers = int(gru_layers)
            self.gru_hidden = int(channels)
            self.gru = nn.GRU(eff_channels, channels, num_layers=self.gru_layers, batch_first=True)
            self.blocks = None
        else:
            blocks, in_ch = [], eff_channels
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
        # GRU has no fixed receptive field (that is the point -- see class docstring); -1 flags
        # "unbounded/stateful" to any caller that logs this field, instead of a misleading number.
        self.receptive_field = -1 if arch == "gru" else 1 + 2 * (kernel_size - 1) * sum(dilations)
        self.register_buffer("input_scale", torch.ones(eff_channels))
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
        """``[B, T, 6]`` -> per-step causal features ``[B, C, T]``.

        The public input is always the raw 6-channel window; when ``derive_magnitude_channels`` is
        set, ``|acc|``/``|gyr|`` at each timestep (same-timestep only, causal, no lookahead) are
        appended before normalization and the conv blocks -- see ``__init__``.
        """
        if x.ndim != 3 or x.shape[-1] != N_CHANNELS:
            raise ValueError(f"expected [B, T, {N_CHANNELS}], got {tuple(x.shape)}")
        if self.derive_magnitude_channels:
            acc_mag = x[..., 0:3].norm(dim=-1, keepdim=True)
            gyr_mag = x[..., 3:6].norm(dim=-1, keepdim=True)
            x = torch.cat([x, acc_mag, gyr_mag], dim=-1)
        x = x / self.input_scale
        if self.arch == "gru":
            out, _ = self.gru(x)  # [B, T, H]; zero initial hidden state, matches windowed training
            return out.transpose(1, 2)  # [B, H, T], same layout convention as the conv path
        return self.blocks(x.transpose(1, 2))

    def forward_full(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor | None]:
        """``(mean_mps [B], log_var_mps2 [B] or None)``. ``log_var_mps2`` is ``None`` unless this
        model was built with ``uncertainty=True``; when present it is already clamped (see class
        docstring), so ``exp()`` of it, or of its negation, is always finite and positive."""
        h = self.features(x)
        pooled = h.mean(dim=2) if self.arch == "cnn" else h[:, :, -1]
        return self._head_from_pooled(pooled)

    def _head_from_pooled(self, pooled: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor | None]:
        mean = self.target_mean + self.target_std * self.head(pooled).squeeze(-1)
        if not self.uncertainty:
            return mean, None
        raw_log_var = torch.clamp(self.log_var_head(pooled).squeeze(-1), self.log_var_min, self.log_var_max)
        log_var_mps2 = 2.0 * torch.log(self.target_std) + raw_log_var
        return mean, log_var_mps2

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.forward_full(x)[0]

    def step(self, x_t: torch.Tensor, h_prev: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor | None, torch.Tensor]:
        """Single-timestep streaming update (``arch="gru"`` only): ``x_t`` is one new sample
        ``[B, 1, 6]`` at the model's native rate, ``h_prev`` is the hidden state carried over from
        the previous call (``[gru_layers, B, gru_hidden]``; zeros for a cold start / after a
        Member 2 discontinuity, exactly like resetting ``ProductionWindowBuffer``).

        This is what lets the deployed model track velocity through an extended,
        near-zero-acceleration cruise that is far longer than any single training window: unlike
        the fixed causal-conv receptive field, ``h_prev`` is not bounded to a fixed window length --
        it is Member 1's entire, continuously-updated internal estimate of the vehicle's dynamic
        state since the last discontinuity. Returns ``(mean_mps [B], log_var_mps2 [B] or None,
        h_next [gru_layers, B, gru_hidden])``.
        """
        if self.arch != "gru":
            raise ValueError("step() is only defined for arch='gru'")
        if x_t.ndim != 3 or x_t.shape[1] != 1 or x_t.shape[-1] != N_CHANNELS:
            raise ValueError(f"expected x_t of shape [B, 1, {N_CHANNELS}], got {tuple(x_t.shape)}")
        if self.derive_magnitude_channels:
            acc_mag = x_t[..., 0:3].norm(dim=-1, keepdim=True)
            gyr_mag = x_t[..., 3:6].norm(dim=-1, keepdim=True)
            x_t = torch.cat([x_t, acc_mag, gyr_mag], dim=-1)
        out, h_next = self.gru(x_t / self.input_scale, h_prev)
        mean, log_var = self._head_from_pooled(out[:, -1, :])
        return mean, log_var, h_next


def build_model(arch: str, model_cfg: dict[str, Any]) -> VelocityNet:
    """Build from the ``models.<arch>`` config section. ``uncertainty`` defaults to ``False`` (the
    Milestone 2 point-estimate behaviour) so existing configs and checkpoints are unaffected.

    ``"cnn_mag"`` is a config-selection alias for ``"cnn"`` (non-dilated blocks, mean-pool readout):
    it exists only so ``models.cnn_mag`` in ``configs/member1.yaml`` can set
    ``derive_magnitude_channels: true`` independently of the plain ``models.cnn`` section, without
    a new architecture family -- ``VelocityNet.arch`` is still ``"cnn"`` either way.
    """
    base_arch = "cnn" if arch in ("cnn", "cnn_mag") else arch
    if base_arch == "cnn":
        dilations = [1] * int(model_cfg["n_blocks"])
    elif base_arch == "tcn":
        dilations = [int(d) for d in model_cfg["dilations"]]
    elif base_arch == "gru":
        dilations = []
    else:
        raise ValueError(f"unknown arch {arch!r}")
    return VelocityNet(base_arch, int(model_cfg["channels"]), int(model_cfg.get("kernel_size", 1)), dilations,
                       float(model_cfg.get("dropout", 0.0)),
                       bool(model_cfg.get("uncertainty", False)), float(model_cfg.get("log_var_min", -6.0)),
                       float(model_cfg.get("log_var_max", 6.0)), bool(model_cfg.get("derive_magnitude_channels", False)),
                       int(model_cfg.get("gru_layers", 1)))


def log_var_to_sigma(log_var_mps2: torch.Tensor) -> torch.Tensor:
    """Native-units log-variance -> predictive standard deviation (m/s)."""
    return torch.exp(0.5 * log_var_mps2)


def fit_normalization(train_imu: np.ndarray, train_targets: np.ndarray,
                       derive_magnitude_channels: bool = False) -> tuple[np.ndarray, float, float]:
    """Fit input scale (per sensor RMS) and target mean/std on TRAINING data only.

    When ``derive_magnitude_channels`` matches the model's own flag, two extra scale entries are
    appended (reusing ``acc_rms``/``gyr_rms``, since ``|acc|``/``|gyr|`` share their source triplet's
    physical units) so the returned array matches ``VelocityNet``'s ``input_scale`` buffer shape.
    """
    acc_rms = float(np.sqrt(np.mean(np.square(train_imu[:, 0:3], dtype=np.float64))))
    gyr_rms = float(np.sqrt(np.mean(np.square(train_imu[:, 3:6], dtype=np.float64))))
    scale = np.array([acc_rms] * 3 + [gyr_rms] * 3, dtype=np.float32)
    if derive_magnitude_channels:
        scale = np.concatenate([scale, [acc_rms, gyr_rms]]).astype(np.float32)
    if not np.all(np.isfinite(scale)) or np.any(scale <= 0):
        raise ValueError(f"invalid input scale {scale}")
    return scale, float(np.mean(train_targets)), float(np.std(train_targets))


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
