"""Shared experiment data preparation: load -> validate -> group split -> window indices.

Used by every experiment script so baselines and neural models see identical data.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from src.data.dataset import ALLOWED_INPUT_KEYS, ImuDataset, check_input_keys, load_npz
from src.data.inspect_dataset import validate
from src.data.splits import SPLIT_NAMES, GroupSplit, make_split
from src.data.windowing import assert_windows_valid, window_end_indices


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def to_json(obj: Any) -> Any:
    """Strict-JSON copy: numpy scalars/arrays -> Python, NaN -> null, +/-inf -> "inf"/"-inf"."""
    if isinstance(obj, dict):
        return {str(k): to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_json(obj.tolist())
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        if np.isnan(obj):
            return None
        if np.isinf(obj):
            return "inf" if obj > 0 else "-inf"
    return obj


def write_json(obj: Any, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(to_json(obj), indent=2, allow_nan=False), encoding="utf-8")


@dataclass(frozen=True)
class PreparedData:
    dataset: ImuDataset
    split: GroupSplit
    subsets: dict[str, ImuDataset]  # split name -> rows of that split only (sessions stay contiguous)

    def split_info(self) -> dict[str, Any]:
        return {"trips": self.split.trips, "sessions": self.split.sessions,
                "unassigned_trips": self.split.unassigned_trips,
                "rows": {s: int(self.split.masks[s].sum()) for s in SPLIT_NAMES}}


def prepare_data(cfg: dict[str, Any], root: Path, verbose: bool = True) -> PreparedData:
    """Load and validate the NPZ, then apply the configured leakage-checked group split."""
    npz_path = root / cfg["data"]["npz_path"]
    check_input_keys(list(ALLOWED_INPUT_KEYS))  # model inputs are assembled only from these keys inside load_npz
    ds = load_npz(npz_path, target_units=cfg["data"]["target_units"])
    with np.load(npz_path, allow_pickle=False) as z:
        errors = validate({k: z[k] for k in z.files}, ds, cfg["data"]["sample_rate_hz"], cfg["data"]["dt_tolerance_s"])
    if errors:
        raise RuntimeError(f"dataset validation failed: {errors}")
    split = make_split(ds.trip_id, ds.session_id, {s: cfg["splits"][s] for s in SPLIT_NAMES})
    subsets = {s: ds.subset(split.masks[s]) for s in SPLIT_NAMES}
    if verbose:
        print(f"Loaded {len(ds)} rows, {len(np.unique(ds.session_id))} sessions, IMU input shape {ds.imu.shape}")
        for s in SPLIT_NAMES:
            print(f"  {s:5s}: {len(split.trips[s])} trips, {len(split.sessions[s])} sessions, {len(subsets[s])} rows  {split.trips[s]}")
        print(f"  unassigned (excluded): {split.unassigned_trips}")
    return PreparedData(ds, split, subsets)


def split_window_ends(subsets: dict[str, ImuDataset], window: int, cfg: dict[str, Any]) -> dict[str, np.ndarray]:
    """Validated window end indices per split: training stride for train, evaluation stride otherwise."""
    wcfg = cfg["windowing"]
    ends = {}
    for s, sub in subsets.items():
        stride = wcfg["train_stride"] if s == "train" else wcfg["eval_stride"]
        e = window_end_indices(sub, window, stride, cfg["data"]["sample_rate_hz"], cfg["data"]["dt_tolerance_s"])
        assert_windows_valid(sub, e, window)
        ends[s] = e
    return ends


def write_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(to_json(rows))


def with_uncertainty(cfg: dict[str, Any], uncertainty: bool) -> dict[str, Any]:
    """A copy of ``cfg`` with every ``models.<arch>`` dict rebuilt (not mutated) with the given flag.

    ``{**cfg, "models": {...}}`` is used deliberately instead of mutating ``cfg["models"][arch]`` in
    place: ``{**cfg}`` only shallow-copies the top level, so an in-place mutation of the nested
    ``models`` dicts would corrupt every other reference to the same config -- including ``info``
    dicts already returned by earlier ``run_one`` calls and stored for later phases or reporting,
    which happened in practice the first time this config was threaded through multiple training
    phases in one process (see ``scripts/run_uncertainty.py``).
    """
    return {**cfg, "models": {arch: {**model_cfg, "uncertainty": uncertainty} for arch, model_cfg in cfg["models"].items()}}
