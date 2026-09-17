"""ONNX export and verification for the deployed :class:`~src.models.tcn_velocity.VelocityNet`.

:class:`InferenceModule` wraps a trained checkpoint's ``forward_full`` in exactly the math
``src.inference.predict.predict_contract`` uses to build the Member 1 -> Member 3 output contract:
the mean clipped to ``>= 0``, sigma from the model's own clamped log-variance, and confidence from
the model's own ``confidence_ref_sigma`` buffer (fit once after training, see
``docs/member1_output_contract.md``). Exporting this wrapper -- instead of the bare model -- means
the ONNX graph reproduces ``velocity_mps``/``uncertainty``/``confidence`` directly; only
``timestamp`` is left out, because it is never a model output (the caller's IMU stream supplies it,
in `predict_contract` and in a live deployment alike).

This module only exports and verifies an already-trained PyTorch checkpoint. It does not train,
select a model, or touch any data split -- ``scripts/export_onnx.py`` is the CLI entry point that
loads a checkpoint and calls the functions here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from src.models.tcn_velocity import VelocityNet

INPUT_NAME = "imu_window"
OUTPUT_NAMES_POINT: tuple[str, ...] = ("velocity_mps",)
OUTPUT_NAMES_UNCERTAINTY: tuple[str, ...] = ("velocity_mps", "uncertainty", "confidence")


class InferenceModule(nn.Module):
    """Wraps a trained :class:`VelocityNet` so its forward pass returns exactly the numeric fields
    of the Member 1 output contract (everything except ``timestamp``, which is not a model output).

    ``forward(x)`` returns ``velocity_mps [B]`` alone for a point model (``model.uncertainty is
    False``), or ``(velocity_mps [B], uncertainty [B], confidence [B])`` for an uncertainty model --
    a fixed output arity per model, which is what ONNX export requires.
    """

    def __init__(self, model: VelocityNet):
        super().__init__()
        self.model = model.eval()
        self.uncertainty = bool(model.uncertainty)

    def forward(self, x: torch.Tensor):
        mean, log_var = self.model.forward_full(x)
        velocity = torch.clamp(mean, min=0.0)
        if not self.uncertainty:
            return velocity
        sigma = torch.exp(0.5 * log_var)
        confidence = self.model.confidence_from_sigma(sigma)
        return velocity, sigma, confidence


def output_names(model: VelocityNet) -> tuple[str, ...]:
    return OUTPUT_NAMES_UNCERTAINTY if model.uncertainty else OUTPUT_NAMES_POINT


def export_model(model: VelocityNet, window: int, path: str | Path, opset: int = 17) -> Path:
    """Export ``model`` to ONNX at ``path``, with a dynamic batch axis.

    The window length ``T`` is fixed at export time, matching how ``window`` is always a fixed
    config value throughout this repo (20 or 40 samples), never inferred at inference time -- only
    the batch dimension varies at deployment.
    """
    model = model.eval()
    wrapper = InferenceModule(model).eval()
    dummy = torch.zeros(1, window, 6, dtype=torch.float32)
    names = output_names(model)
    dynamic_axes = {INPUT_NAME: {0: "batch"}, **{n: {0: "batch"} for n in names}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(
            wrapper, (dummy,), str(path),
            input_names=[INPUT_NAME], output_names=list(names), dynamic_axes=dynamic_axes,
            opset_version=opset, do_constant_folding=True, dynamo=False,
        )
    return path


def load_onnx_session(path: str | Path, intra_op_num_threads: int | None = None, inter_op_num_threads: int | None = None):
    """CPU-only ONNX Runtime session (the deployment target Member 5 integrates via C++20 +
    ONNX Runtime is CPU, not GPU -- see ``docs/architecture.md``).

    ``intra_op_num_threads``/``inter_op_num_threads`` default to ONNX Runtime's own auto-detected
    thread count when left ``None``. For single-window (batch=1) latency measurement, pass ``1`` for
    both: this model is small enough that multi-threaded dispatch overhead can dominate its actual
    compute time, which would overstate real per-window latency relative to a lean single/few-thread
    embedded deployment (Member 5's C++20 + ONNX Runtime target) -- see
    ``scripts/export_onnx.py``, which measures it this way.
    """
    import onnxruntime as ort
    options = ort.SessionOptions()
    if intra_op_num_threads is not None:
        options.intra_op_num_threads = intra_op_num_threads
    if inter_op_num_threads is not None:
        options.inter_op_num_threads = inter_op_num_threads
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def run_onnx(session, x: np.ndarray) -> dict[str, np.ndarray]:
    """Run an ONNX Runtime session on a ``[B, T, 6]`` float32 batch; returns ``{output_name: array}``."""
    x = np.asarray(x, dtype=np.float32)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: x})
    names = [o.name for o in session.get_outputs()]
    return dict(zip(names, outputs))


def run_pytorch(model: VelocityNet, x: np.ndarray) -> dict[str, np.ndarray]:
    """Run the same :class:`InferenceModule` wrapper in plain PyTorch, for comparison with ONNX."""
    wrapper = InferenceModule(model).eval()
    with torch.no_grad():
        out = wrapper(torch.as_tensor(np.asarray(x, dtype=np.float32)))
    if not isinstance(out, tuple):
        out = (out,)
    return {n: t.numpy() for n, t in zip(output_names(model), out)}


def compare_pytorch_onnx(model: VelocityNet, session, x: np.ndarray, atol: float = 1e-4,
                          rtol: float = 1e-3) -> dict[str, Any]:
    """Per-output PyTorch vs ONNX Runtime numerical agreement on the same input batch."""
    torch_out = run_pytorch(model, x)
    onnx_out = run_onnx(session, x)
    report: dict[str, Any] = {}
    for name in torch_out:
        t, o = torch_out[name], onnx_out[name]
        if t.shape != o.shape:
            raise ValueError(f"{name}: shape mismatch pytorch {t.shape} vs onnx {o.shape}")
        diff = np.abs(t - o)
        report[name] = {
            "max_abs_diff": float(diff.max()) if diff.size else 0.0,
            "mean_abs_diff": float(diff.mean()) if diff.size else 0.0,
            "allclose": bool(np.allclose(t, o, atol=atol, rtol=rtol)),
            "finite_pytorch": bool(np.isfinite(t).all()),
            "finite_onnx": bool(np.isfinite(o).all()),
        }
    return report


def verify_shapes_and_finite(session, window: int, batch_sizes: tuple[int, ...] = (1, 8, 64),
                              seed: int = 0) -> dict[str, Any]:
    """Run the ONNX session at several batch sizes: checks dynamic-batch support, output shapes and
    finiteness (no NaN/Inf), independent of any PyTorch comparison."""
    rng = np.random.default_rng(seed)
    report: dict[str, Any] = {}
    for b in batch_sizes:
        x = rng.standard_normal((b, window, 6)).astype(np.float32)
        out = run_onnx(session, x)
        report[str(b)] = {}
        for name, arr in out.items():
            if arr.shape[0] != b:
                raise ValueError(f"batch {b}: output {name!r} has batch dim {arr.shape[0]}")
            report[str(b)][name] = {"shape": list(arr.shape), "finite": bool(np.isfinite(arr).all())}
    return report
