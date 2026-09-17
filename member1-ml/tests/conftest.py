from __future__ import annotations

import numpy as np
import pytest


def make_arrays(sessions: dict[str, tuple[str, int]], seed: int = 0) -> dict[str, np.ndarray]:
    """Synthetic NPZ-style arrays. ``sessions`` maps session_id -> (trip_id, n_rows)."""
    rng = np.random.default_rng(seed)
    parts: dict[str, list[np.ndarray]] = {k: [] for k in ("acc", "gyr", "target_speed_mps", "t_session_s",
                                                          "session_id", "trip_id", "sample_idx", "verdict")}
    for sid, (trip, n) in sessions.items():
        speed = np.clip(np.cumsum(rng.normal(0, 0.3, n)) + 10.0, 0, None).astype(np.float32)
        acc = rng.normal(0, 0.5, (n, 3)).astype(np.float32)
        acc[:, 2] += 9.81
        acc[:, 0] += np.gradient(speed) * 10.0
        parts["acc"].append(acc)
        parts["gyr"].append(rng.normal(0, 0.05, (n, 3)).astype(np.float32))
        parts["target_speed_mps"].append(speed)
        parts["t_session_s"].append((np.arange(n) * 0.1 + 1.0).astype(np.float32))
        parts["session_id"].append(np.full(n, sid, dtype="<U10"))
        parts["trip_id"].append(np.full(n, trip, dtype="<U5"))
        parts["sample_idx"].append(np.arange(n, dtype=np.int64))
        parts["verdict"].append(np.full(n, "GOOD", dtype="<U4"))
    return {k: np.concatenate(v) for k, v in parts.items()}


SESSIONS = {
    "Vw2__s00": ("Vw2", 120), "Vw4__s00": ("Vw4", 90), "Vfa02__s00": ("Vfa02", 80), "Vfa01__s00": ("Vfa01", 50),
    "M__s01": ("M", 70), "M__s02": ("M", 60), "S1__s00": ("S1", 75), "S3a__s00": ("S3a", 65), "Y1__s00": ("Y1", 40),
}
SPLIT_RULES = {"train": [r"Vw\d+[a-z]?", "Vfa02"], "val": ["M"], "test": [r"S\d+[a-z]?"]}


@pytest.fixture
def arrays() -> dict[str, np.ndarray]:
    return make_arrays(SESSIONS)


@pytest.fixture
def npz_path(tmp_path, arrays):
    path = tmp_path / "synthetic.npz"
    np.savez(path, **arrays)
    return path
