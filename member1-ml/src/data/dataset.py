"""Loading of the Member 1 NPZ with leakage-safe separation of model inputs.

The NPZ (``data/member1_imu_speed.npz``) is a flat, row-per-sample table:

    acc               (N, 3) float32  smartphone accelerometer XYZ
    gyr               (N, 3) float32  smartphone gyroscope XYZ
    target_speed_mps  (N,)   float32  vehicle speed, m/s (supervised target only)
    t_session_s       (N,)   float32  seconds since session start (continuity checks only)
    session_id        (N,)   <U10     e.g. "Vw4__s00" (grouping only)
    trip_id           (N,)   <U5      e.g. "Vw4" (grouping only)
    sample_idx        (N,)   int64    per-session sample counter (continuity checks only)
    verdict           (N,)   <U4      per-session quality tag "GOOD"/"OK" (metadata only)

Only ``acc`` and ``gyr`` may ever reach a model. This is enforced in
:func:`build_model_input`, which is the single place IMU input arrays are assembled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Channel order of every model input tensor: [acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z].
ALLOWED_INPUT_KEYS: tuple[str, ...] = ("acc", "gyr")
IMU_CHANNELS: tuple[str, ...] = ("acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z")
TARGET_KEY = "target_speed_mps"
META_KEYS: tuple[str, ...] = ("session_id", "trip_id", "sample_idx", "t_session_s", "verdict")
REQUIRED_KEYS: tuple[str, ...] = ALLOWED_INPUT_KEYS + (TARGET_KEY, "session_id", "trip_id", "sample_idx", "t_session_s")

# Case-insensitive patterns that must never appear in a model-input key.
FORBIDDEN_INPUT_PATTERNS: tuple[str, ...] = (
    r"^veh", r"wheel", r"yaw", r"heading", r"indicated", r"speed", r"velocity", r"target",
    r"gps", r"lat", r"lon", r"accuracy", r"orient", r"bearing", r"mag",
    r"trip", r"session", r"verdict", r"date", r"time", r"^t_", r"has_ground_truth", r"outage",
    r"sample_idx",
)


class LeakageError(ValueError):
    """Raised when a forbidden field is requested as a model input."""


def check_input_keys(keys: tuple[str, ...] | list[str]) -> None:
    """Raise :class:`LeakageError` unless every key is an allowed IMU key."""
    for key in keys:
        hits = [p for p in FORBIDDEN_INPUT_PATTERNS if re.search(p, key, flags=re.IGNORECASE)]
        if hits or key not in ALLOWED_INPUT_KEYS:
            raise LeakageError(f"Key {key!r} is not an allowed model input (allowed: {ALLOWED_INPUT_KEYS}; matched forbidden {hits})")


def build_model_input(arrays: dict[str, np.ndarray], keys: tuple[str, ...] = ALLOWED_INPUT_KEYS) -> np.ndarray:
    """Stack the allowed IMU arrays into a float32 ``(N, 6)`` matrix after the leakage check."""
    check_input_keys(keys)
    parts = [np.asarray(arrays[k], dtype=np.float32) for k in keys]
    for k, p in zip(keys, parts):
        if p.ndim != 2 or p.shape[1] != 3:
            raise ValueError(f"{k!r} must have shape (N, 3), got {p.shape}")
    imu = np.concatenate(parts, axis=1)
    if imu.shape[1] != len(IMU_CHANNELS):
        raise ValueError(f"Expected {len(IMU_CHANNELS)} IMU channels, got {imu.shape[1]}")
    return imu


@dataclass(frozen=True)
class ImuDataset:
    """IMU inputs, target and grouping metadata, row-aligned. Only ``imu`` is model input."""

    imu: np.ndarray          # (N, 6) float32
    target: np.ndarray       # (N,)   float32, m/s
    session_id: np.ndarray   # (N,)   str
    trip_id: np.ndarray      # (N,)   str
    sample_idx: np.ndarray   # (N,)   int64
    t_session_s: np.ndarray  # (N,)   float64

    def __len__(self) -> int:
        return len(self.target)

    def subset(self, mask: np.ndarray) -> "ImuDataset":
        return ImuDataset(*(getattr(self, f)[mask] for f in self.__dataclass_fields__))


def from_arrays(arrays: dict[str, np.ndarray], target_units: str = "m/s") -> ImuDataset:
    """Build an :class:`ImuDataset` from a dict of NPZ-style arrays (also used by test fixtures)."""
    missing = [k for k in REQUIRED_KEYS if k not in arrays]
    if missing:
        raise KeyError(f"Dataset is missing required keys: {missing}")
    target = np.asarray(arrays[TARGET_KEY], dtype=np.float32)
    if target_units == "km/h":
        target = target / np.float32(3.6)
    elif target_units != "m/s":
        raise ValueError(f"Unsupported target units {target_units!r}")
    ds = ImuDataset(
        imu=build_model_input(arrays),
        target=target,
        session_id=np.asarray(arrays["session_id"]).astype(str),
        trip_id=np.asarray(arrays["trip_id"]).astype(str),
        sample_idx=np.asarray(arrays["sample_idx"], dtype=np.int64),
        t_session_s=np.asarray(arrays["t_session_s"], dtype=np.float64),
    )
    n = len(ds.target)
    for name in ds.__dataclass_fields__:
        if len(getattr(ds, name)) != n:
            raise ValueError(f"Field {name!r} has length {len(getattr(ds, name))}, expected {n}")
    return ds


def load_npz(path: str | Path, target_units: str = "m/s") -> ImuDataset:
    """Load the NPZ read-only (the file is never modified)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    return from_arrays(arrays, target_units=target_units)
