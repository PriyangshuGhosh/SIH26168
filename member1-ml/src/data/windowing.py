"""Causal, session-safe sliding windows over the flat row-per-sample dataset.

A window of length ``T`` ending at row ``e`` covers rows ``[e - T + 1, e]`` and is labelled
with the target at row ``e`` (the prediction point). No sample after ``e`` is used, so the
windows are causal by construction.

Windows are represented by their end indices (``int64`` array of shape ``(M,)``) into the
flat arrays; :func:`gather_windows` materialises them as ``float32`` tensors of shape
``(M, T, 6)`` = ``[B, T, C]`` with channels ``[acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z]``.
Keeping indices instead of tensors lets stride-1 evaluation over hundreds of thousands of
windows be processed in chunks.

A window is valid only if:
  * all its rows belong to one session (never crosses a session boundary);
  * consecutive rows are contiguous: ``sample_idx`` increments by 1 and the time step is
    ``1 / sample_rate_hz`` within ``dt_tolerance_s``;
  * every IMU value in the window is finite;
  * the target at the prediction point is finite.

Within each session, candidate ends are placed at in-session positions
``T - 1, T - 1 + stride, ...``; invalid candidates are dropped (not shifted).
"""
from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from src.data.dataset import ImuDataset

SAMPLE_RATE_HZ = 10.0


def seconds_to_samples(seconds: float, sample_rate_hz: float = SAMPLE_RATE_HZ) -> int:
    n = round(seconds * sample_rate_hz)
    if not np.isclose(n, seconds * sample_rate_hz):
        raise ValueError(f"{seconds}s at {sample_rate_hz}Hz is not an integer number of samples")
    return int(n)


def session_starts(session_id: np.ndarray) -> np.ndarray:
    """Boolean ``(N,)``: True where a row begins a new session block."""
    starts = np.ones(len(session_id), dtype=bool)
    starts[1:] = session_id[1:] != session_id[:-1]
    return starts


def break_mask(ds: ImuDataset, sample_rate_hz: float = SAMPLE_RATE_HZ, dt_tolerance_s: float = 0.02) -> np.ndarray:
    """Boolean ``(N,)``: True where row ``i`` is not a contiguous continuation of row ``i-1``."""
    brk = session_starts(ds.session_id)
    dt = np.diff(ds.t_session_s)
    dsi = np.diff(ds.sample_idx)
    brk[1:] |= (dsi != 1) | ~np.isfinite(dt) | (np.abs(dt - 1.0 / sample_rate_hz) > dt_tolerance_s)
    return brk


def window_end_indices(
    ds: ImuDataset,
    window: int,
    stride: int,
    sample_rate_hz: float = SAMPLE_RATE_HZ,
    dt_tolerance_s: float = 0.02,
) -> np.ndarray:
    """Return sorted ``int64`` end indices of all valid causal windows of length ``window``."""
    if window < 1 or stride < 1:
        raise ValueError("window and stride must be >= 1")
    n = len(ds)
    if n < window:
        return np.empty(0, dtype=np.int64)
    idx = np.arange(n)
    starts = session_starts(ds.session_id)
    session_first_row = np.maximum.accumulate(np.where(starts, idx, 0))
    pos = idx - session_first_row

    candidate = (pos >= window - 1) & ((pos - (window - 1)) % stride == 0)

    # Prefix sums: a window [e-T+1, e] is clean iff it has no bad IMU row and no break
    # strictly after its first row (a break *at* its first row is allowed).
    bad_imu = ~np.isfinite(ds.imu).all(axis=1)
    brk = break_mask(ds, sample_rate_hz, dt_tolerance_s)
    cum_bad = np.concatenate([[0], np.cumsum(bad_imu)])
    cum_brk = np.concatenate([[0], np.cumsum(brk)])

    ends = idx[candidate]
    first = ends - window + 1
    n_bad = cum_bad[ends + 1] - cum_bad[first]
    n_brk = cum_brk[ends + 1] - cum_brk[first + 1]
    ok = (n_bad == 0) & (n_brk == 0) & np.isfinite(ds.target[ends])
    return ends[ok].astype(np.int64)


def gather_windows(imu: np.ndarray, ends: np.ndarray, window: int) -> np.ndarray:
    """Materialise windows: ``imu (N, C)`` + ``ends (M,)`` -> ``float32 (M, window, C)``."""
    offsets = np.arange(-window + 1, 1)
    return imu[ends[:, None] + offsets[None, :]].astype(np.float32, copy=False)


def iter_window_chunks(imu: np.ndarray, ends: np.ndarray, window: int, chunk_size: int = 50_000) -> Iterator[np.ndarray]:
    """Yield ``(m, window, C)`` window tensors in order, ``m <= chunk_size``."""
    for s in range(0, len(ends), chunk_size):
        yield gather_windows(imu, ends[s:s + chunk_size], window)


def assert_windows_valid(ds: ImuDataset, ends: np.ndarray, window: int) -> None:
    """Independent (slow-path) re-check that windows are causal, single-session and contiguous."""
    if len(ends) == 0:
        return
    assert np.all(np.diff(ends) > 0), "window ends must be strictly increasing"
    first = ends - window + 1
    assert np.all(first >= 0), "window starts before row 0"
    assert np.all(ds.session_id[first] == ds.session_id[ends]), "window crosses a session boundary"
    assert np.all(ds.sample_idx[ends] - ds.sample_idx[first] == window - 1), "window is not contiguous"
    assert np.all(np.isfinite(ds.target[ends])), "non-finite target at prediction point"
