"""Regression losses for speed in m/s: point losses, and the heteroscedastic Gaussian NLL.

Point losses (Milestone 2) train a mean-only predictor. The heteroscedastic Gaussian NLL
(Milestone 3) additionally trains a per-window log-variance head, giving a predictive
uncertainty rather than a single point estimate. It requires ``log_var`` produced by
:meth:`src.models.tcn_velocity.VelocityNet.forward_full`, which is already clamped to a bounded
range before this loss ever sees it -- ``exp()`` of a bounded input cannot overflow or vanish to
zero, which is what makes the whole parameterization numerically stable even from a random init.
"""
from __future__ import annotations

import math
from collections.abc import Callable

import torch
from torch.nn import functional as F

LossFn = Callable[[torch.Tensor, torch.Tensor], torch.Tensor]
UncertaintyLossFn = Callable[[torch.Tensor, torch.Tensor, torch.Tensor], torch.Tensor]

_LOG_2PI = math.log(2.0 * math.pi)


def make_loss(name: str, huber_delta_mps: float = 1.0) -> LossFn:
    """``"mse"``, ``"l1"`` or ``"huber"`` (quadratic below ``huber_delta_mps``, linear above). Mean over batch."""
    if name == "mse":
        return lambda pred, target: F.mse_loss(pred, target)
    if name == "l1":
        return lambda pred, target: F.l1_loss(pred, target)
    if name == "huber":
        if huber_delta_mps <= 0:
            raise ValueError("huber_delta_mps must be > 0")
        return lambda pred, target: F.huber_loss(pred, target, delta=huber_delta_mps)
    raise ValueError(f"unknown loss {name!r}")


def heteroscedastic_gaussian_nll(mean: torch.Tensor, log_var: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Mean heteroscedastic Gaussian negative log-likelihood, in native (m/s, m^2/s^2) units.

    ``NLL = 0.5 * (log_var + (target - mean)^2 * exp(-log_var) + log(2*pi))``, averaged over the
    batch. ``log_var`` must already be clamped upstream (as ``VelocityNet.forward_full`` does), so
    ``exp(-log_var)`` is always finite here -- this function does no clamping of its own.
    """
    inv_var = torch.exp(-log_var)
    nll = 0.5 * (log_var + (target - mean) ** 2 * inv_var + _LOG_2PI)
    return nll.mean()


def make_uncertainty_loss(name: str) -> UncertaintyLossFn:
    """``"nll"`` is the only supported heteroscedastic loss for now."""
    if name == "nll":
        return heteroscedastic_gaussian_nll
    raise ValueError(f"unknown uncertainty loss {name!r}")
