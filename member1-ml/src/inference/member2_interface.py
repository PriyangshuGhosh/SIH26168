"""Production Member 2 -> Member 1 interface: consumes Member 2's actual ``AlignedIMUFrame`` stream
at its genuine 100 Hz rate and turns it into the model's native-resolution input.

Why this module exists (see ``docs/production_100hz.md`` for the full writeup): the Member 1 model
is trained and validated only on the project's real IO-VNBD-derived dataset
(``data/member1_imu_speed.npz``), which is natively and consistently sampled at 10 Hz (verified by
``src.data.inspect_dataset``) -- there is no genuine 100 Hz IMU recording anywhere in this repo to
train or validate a native-100Hz model against. Fabricating one by upsampling the 10 Hz training data
would create training/eval windows with interpolated samples the sensor never produced, which is
exactly the "claim 10 Hz data is native 100 Hz" mistake this module avoids.

Member 2 (``docs/member2/INTEGRATION.md``) genuinely runs at 100 Hz in production
(``FrameAlignerConfig.sample_rate_hz == 100.0``) and is not being changed here. The resolution this
module makes is the other direction, which does not fabricate anything: it accepts Member 2's real
100 Hz stream and *decimates* it down to the 10 Hz resolution the shipped model actually understands,
by keeping the most recent (causal) real sample out of every 10 -- i.e. exactly the samples a genuine
10 Hz sensor would have produced at those instants, never an interpolated value. This is a resampling
*interface* fix, not a retraining of the model on invented data: :mod:`src.models.tcn_velocity` and
the training/evaluation pipeline are untouched.

The production causal window is 200 raw Member-2 frames (2 s at 100 Hz), matching the project's
100 Hz input contract at the interface boundary; after decimation this is exactly 20 samples at
10 Hz, i.e. ``configs/member1.yaml``'s ``window_sizes: [20, ...]`` variant (2 s at the model's native
rate) -- not the 40-sample (4 s) variant, which would need a 400-sample raw buffer. A model exported
for the production path must therefore be one trained with ``window: 20``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from src.data.windowing import SAMPLE_RATE_HZ as MODEL_SAMPLE_RATE_HZ

# Member 2's genuine production rate (matches sih26168_alignment.types.FrameAlignerConfig.sample_rate_hz).
PRODUCTION_SAMPLE_RATE_HZ = 100.0
PRODUCTION_WINDOW_SECONDS = 2.0
PRODUCTION_RAW_WINDOW = round(PRODUCTION_SAMPLE_RATE_HZ * PRODUCTION_WINDOW_SECONDS)  # 200

# Member 2's CalibrationStatus.FULLY_ALIGNED (see sih26168_alignment.types.CalibrationStatus / docs/member2).
FULLY_ALIGNED = 4

if not np.isclose(PRODUCTION_RAW_WINDOW / (PRODUCTION_SAMPLE_RATE_HZ / MODEL_SAMPLE_RATE_HZ),
                   round(PRODUCTION_RAW_WINDOW / (PRODUCTION_SAMPLE_RATE_HZ / MODEL_SAMPLE_RATE_HZ))):
    raise AssertionError("PRODUCTION_RAW_WINDOW must decimate to an integer number of model-rate samples")
DECIMATION_FACTOR = round(PRODUCTION_SAMPLE_RATE_HZ / MODEL_SAMPLE_RATE_HZ)  # 10
MODEL_NATIVE_WINDOW = PRODUCTION_RAW_WINDOW // DECIMATION_FACTOR  # 20 samples = 2 s at 10 Hz


@runtime_checkable
class AlignedIMUFrameLike(Protocol):
    """Structural interface of Member 2's ``AlignedIMUFrame`` (``sih26168_alignment.types``).

    Duck-typed deliberately: this module does not import ``sih26168_alignment`` (Member 2's package
    is not a runtime dependency of Member 1), so any object with these attributes works -- the real
    dataclass, a pybind11 C++ wrapper, or a test double.
    """

    timestamp: float
    ax_v: float
    ay_v: float
    az_v: float
    gx_v: float
    gy_v: float
    gz_v: float
    status: object  # int or CalibrationStatus; compared via is_fully_aligned()


def is_fully_aligned(frame: AlignedIMUFrameLike) -> bool:
    """``True`` iff ``frame.status`` is Member 2's ``CalibrationStatus.FULLY_ALIGNED`` (value 4).

    Per ``docs/member2/INTEGRATION.md``: "Consume only samples with status == FULLY_ALIGNED for
    training/inference of v_x." Any other status means the vehicle-frame axes are not trustworthy.
    """
    return int(frame.status) == FULLY_ALIGNED


def frame_to_channels(frame: AlignedIMUFrameLike) -> np.ndarray:
    """Extract exactly the 6 model-input channels from a frame, in the trained channel order.

    Reads only ``ax_v, ay_v, az_v, gx_v, gy_v, gz_v`` -- never ``timestamp``, ``status``, ``q_pv`` or
    ``confidence`` -- mirroring the leakage discipline ``src/data/dataset.py::build_model_input``
    enforces for the training data (only ``acc``/``gyr`` may reach the model).
    """
    return np.array([frame.ax_v, frame.ay_v, frame.az_v, frame.gx_v, frame.gy_v, frame.gz_v], dtype=np.float32)


def decimate(raw: np.ndarray, factor: int = DECIMATION_FACTOR) -> np.ndarray:
    """``[raw_window, 6]`` at ``PRODUCTION_SAMPLE_RATE_HZ`` -> ``[raw_window // factor, 6]`` at
    ``MODEL_SAMPLE_RATE_HZ``, keeping the most recent real sample of every ``factor``-sized block
    (``raw[factor - 1 :: factor]``). Causal: every kept sample's timestamp is <= the window end, and
    no sample is interpolated or fabricated -- this only drops real samples, it never invents one."""
    if raw.ndim != 2 or raw.shape[1] != 6:
        raise ValueError(f"expected raw window of shape (N, 6), got {raw.shape}")
    if raw.shape[0] % factor != 0:
        raise ValueError(f"raw window length {raw.shape[0]} is not a multiple of decimation factor {factor}")
    return raw[factor - 1::factor]


def production_window_to_model_input(raw: np.ndarray) -> np.ndarray:
    """``[PRODUCTION_RAW_WINDOW, 6]`` raw 100 Hz window -> ``[MODEL_NATIVE_WINDOW, 6]`` float32 model input."""
    if raw.shape[0] != PRODUCTION_RAW_WINDOW:
        raise ValueError(f"expected {PRODUCTION_RAW_WINDOW} raw samples (2 s at {PRODUCTION_SAMPLE_RATE_HZ:g} Hz), "
                          f"got {raw.shape[0]}")
    return decimate(raw).astype(np.float32, copy=False)


@dataclass
class ProductionWindowBuffer:
    """Causal ring buffer over a live ``AlignedIMUFrame`` stream: accumulates the last
    ``raw_window`` (default 200, i.e. 2 s at 100 Hz) samples and yields a model-ready window every
    ``stride`` frames once full.

    ``stride`` defaults to ``DECIMATION_FACTOR`` (10), i.e. one emission every 100 ms -- the model's
    own native 10 Hz cadence (``configs/member1.yaml``'s ``eval_stride: 1`` at 10 Hz) and the
    "recommended prediction stride: 10 samples [at 100 Hz]" from ``docs/WORK_DISTRIBUTION.md``.
    Emitting at every single 100 Hz frame instead would produce predictions at a resolution never
    exercised in training or evaluation.

    Not thread-safe, matching Member 2's own ``FrameAligner`` (``docs/member2/INTEGRATION.md``:
    "not internally synchronized"). One buffer per stream.
    """

    raw_window: int = PRODUCTION_RAW_WINDOW
    stride: int = DECIMATION_FACTOR
    _rows: deque = field(init=False, repr=False)
    _since_emit: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.raw_window % DECIMATION_FACTOR != 0:
            raise ValueError(f"raw_window {self.raw_window} must be a multiple of {DECIMATION_FACTOR}")
        if self.stride < 1:
            raise ValueError("stride must be >= 1")
        self._rows = deque(maxlen=self.raw_window)
        self._since_emit = 0

    def reset(self) -> None:
        """Drop all buffered history. Call on Member 2 ``status`` discontinuity, session start, or
        a caller-detected remount/re-init, exactly when Member 2 itself would move to
        ``REINITIALIZING`` (``docs/member2/STATUS_AND_CONFIDENCE.md``)."""
        self._rows.clear()
        self._since_emit = 0

    def push(self, frame: AlignedIMUFrameLike) -> tuple[np.ndarray, float] | None:
        """Feed one frame (100 Hz cadence). Returns ``(raw_window [raw_window, 6] float32, timestamp)``
        once the buffer is full and ``stride`` frames have passed since the last emission, else
        ``None``.

        A non-``FULLY_ALIGNED`` frame resets the buffer: the window must be entirely trustworthy
        vehicle-frame data (no mixing of aligned and not-yet-aligned history), matching Member 2's own
        guidance to gate consumption on ``status``. A ``FULLY_ALIGNED`` frame whose channels are not
        all finite also resets the buffer: Member 2's own status machine reserves ``INVALID`` for
        exactly this case ("NaN/Inf/time/magnitude" validation failure,
        ``docs/member2/STATUS_AND_CONFIDENCE.md``), so a finite `FULLY_ALIGNED` frame is the contract
        -- this is defense in depth, matching the same finite-value invariant
        ``src.data.windowing.window_end_indices`` enforces on the training data, not a Member 2
        reimplementation.
        """
        if not is_fully_aligned(frame):
            self.reset()
            return None
        channels = frame_to_channels(frame)
        if not np.isfinite(channels).all():
            self.reset()
            return None
        self._rows.append(channels)
        if len(self._rows) < self.raw_window:
            return None
        self._since_emit += 1
        if self._since_emit < self.stride:
            return None
        self._since_emit = 0
        return np.stack(self._rows, axis=0), float(frame.timestamp)
