"""Turns a trained :class:`~src.models.tcn_velocity.VelocityNet` checkpoint's predictions into the
Member 1 -> Member 3 output contract: one record per prediction with ``velocity_mps``,
``uncertainty``, ``confidence`` and ``timestamp``. See ``docs/member1_output_contract.md`` for the
full schema. This module only produces predictions from an already-trained checkpoint -- it does
not train, export to ONNX, or touch any deployment target.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch

from src.models.tcn_velocity import VelocityNet
from src.training.train import predict_indexed, predict_indexed_uncertainty, resolve_device


def predict_contract(
    model: VelocityNet,
    imu: np.ndarray,
    ends: np.ndarray,
    window: int,
    timestamps: np.ndarray,
    device: torch.device | None = None,
    dtype: torch.dtype | None = None,
    batch_size: int = 4096,
    transform: Any = None,
) -> list[dict[str, Any]]:
    """One output-contract record per window end index in ``ends``.

    ``timestamps`` must align 1:1 with ``ends`` and carries whatever time base the caller's IMU
    stream uses (session-relative seconds for the evaluation windows in this repo; device
    wall-clock epoch seconds in a live deployment) -- this function does not interpret or fabricate
    a clock, it only passes the caller's timestamps through into the contract records.

    For a point-only model (``model.uncertainty is False``), ``uncertainty`` and ``confidence`` are
    ``None`` in every record: the model has nothing to report there, and Member 3 must treat a
    ``None`` uncertainty as "no confidence-aware fusion information available" rather than assume
    a numeric default.
    """
    if len(timestamps) != len(ends):
        raise ValueError(f"timestamps ({len(timestamps)}) must align 1:1 with ends ({len(ends)})")
    device = device or resolve_device()
    model = model.to(device).eval()
    if model.uncertainty:
        mean, sigma = predict_indexed_uncertainty(model, imu, ends, window, device, batch_size, dtype, transform=transform)
        # sigma is a CPU numpy array (predict_indexed_uncertainty always returns CPU arrays); the
        # buffer it's compared against lives wherever the model does, so the tensor built from it
        # must be moved there too, or a CUDA model raises a device-mismatch error here.
        sigma_t = torch.as_tensor(sigma, dtype=torch.float32, device=model.confidence_ref_sigma.device)
        confidence = model.confidence_from_sigma(sigma_t).cpu().numpy()
        return [{"velocity_mps": float(v), "uncertainty": float(u), "confidence": float(c), "timestamp": float(ts)}
                for v, u, c, ts in zip(mean, sigma, confidence, timestamps)]
    mean = predict_indexed(model, imu, ends, window, device, batch_size, dtype, transform=transform)
    return [{"velocity_mps": float(v), "uncertainty": None, "confidence": None, "timestamp": float(ts)}
            for v, ts in zip(mean, timestamps)]
