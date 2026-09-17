"""CPU latency, throughput, size and parameter-count benchmarking for the deployed
:class:`~src.models.tcn_velocity.VelocityNet`, in plain PyTorch and in ONNX Runtime.

Kept dependency-light and CPU-only on purpose: the deployment target (Member 5's C++20 +
ONNX Runtime integration, see ``docs/architecture.md``) runs on CPU, and this repo already treats
new dependencies as something to justify (``CLAUDE.md``'s "no unnecessary dependencies" rule) --
process memory is measured only if ``psutil`` happens to be installed, and silently reported as
unavailable (``None``) otherwise, rather than adding it as a new requirement for one optional number.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from src.models.tcn_velocity import VelocityNet, count_parameters


def pytorch_cpu_latency_ms(model: VelocityNet, window: int, batch_size: int = 1, n_warmup: int = 10,
                            n_repeats: int = 200, seed: int = 0, num_threads: int | None = None) -> float:
    """Mean single-batch CPU forward-pass latency (milliseconds), plain PyTorch, eval mode.

    ``num_threads``, if given, temporarily overrides ``torch.get_num_threads()`` for the duration of
    this call (restored afterwards) -- pass ``1`` for a small-batch (e.g. single-window) latency
    number representative of a lean embedded deployment, where multi-threaded dispatch overhead can
    otherwise dominate a model this small's actual compute time. Left ``None``, this uses whatever
    thread count PyTorch is already configured with.
    """
    model = model.to("cpu").eval()
    x = torch.from_numpy(np.random.default_rng(seed).standard_normal((batch_size, window, 6)).astype(np.float32))
    prev_threads = torch.get_num_threads()
    if num_threads is not None:
        torch.set_num_threads(num_threads)
    try:
        with torch.no_grad():
            for _ in range(n_warmup):
                model(x)
            t0 = time.perf_counter()
            for _ in range(n_repeats):
                model(x)
            return (time.perf_counter() - t0) / n_repeats * 1000.0
    finally:
        if num_threads is not None:
            torch.set_num_threads(prev_threads)


def onnx_cpu_latency_ms(session, window: int, batch_size: int = 1, n_warmup: int = 10,
                         n_repeats: int = 200, seed: int = 0) -> float:
    """Mean single-batch CPU inference latency (milliseconds) through ONNX Runtime."""
    input_name = session.get_inputs()[0].name
    x = np.random.default_rng(seed).standard_normal((batch_size, window, 6)).astype(np.float32)
    for _ in range(n_warmup):
        session.run(None, {input_name: x})
    t0 = time.perf_counter()
    for _ in range(n_repeats):
        session.run(None, {input_name: x})
    return (time.perf_counter() - t0) / n_repeats * 1000.0


def throughput_windows_per_s(latency_ms: float, batch_size: int = 1) -> float:
    """Windows processed per second at the given per-batch latency."""
    return batch_size * 1000.0 / latency_ms


def model_size_bytes(path: str | Path) -> int:
    return Path(path).stat().st_size


def process_memory_mb() -> float | None:
    """Current process resident memory (MB), only if ``psutil`` is already installed; ``None``
    otherwise. Not a reliable cross-run measurement (shared with everything else this Python
    process has loaded, e.g. torch/onnxruntime themselves), so treat it as a rough indicator only,
    per the milestone's "if reliably measurable" instruction."""
    try:
        import psutil
    except ImportError:
        return None
    return psutil.Process().memory_info().rss / (1024 * 1024)


def benchmark_report(model: VelocityNet, session, onnx_path: str | Path, window: int, batch_size: int = 1,
                      n_warmup: int = 10, n_repeats: int = 200, num_threads: int | None = None) -> dict[str, Any]:
    """Combined PyTorch + ONNX Runtime CPU benchmark: latency, throughput, size, parameter count.

    ``session`` should already be configured with the thread count the caller wants measured (see
    :func:`src.inference.export_onnx.load_onnx_session`'s ``intra_op_num_threads``); ``num_threads``
    here applies the matching override to the PyTorch side only, for a fair side-by-side number.
    """
    pt_latency = pytorch_cpu_latency_ms(model, window, batch_size, n_warmup, n_repeats, num_threads=num_threads)
    onnx_latency = onnx_cpu_latency_ms(session, window, batch_size, n_warmup, n_repeats)
    size_bytes = model_size_bytes(onnx_path)
    return {
        "n_parameters": count_parameters(model),
        "onnx_model_size_bytes": size_bytes,
        "onnx_model_size_kb": size_bytes / 1024.0,
        "batch_size": batch_size,
        "n_repeats": n_repeats,
        "pytorch_cpu_latency_ms": pt_latency,
        "onnx_cpu_latency_ms": onnx_latency,
        "pytorch_throughput_windows_per_s": throughput_windows_per_s(pt_latency, batch_size),
        "onnx_throughput_windows_per_s": throughput_windows_per_s(onnx_latency, batch_size),
        "process_memory_mb": process_memory_mb(),
    }
