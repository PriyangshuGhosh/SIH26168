"""Reproducible inspection and validation of the Member 1 NPZ.

Usage:
    python -m src.data.inspect_dataset [--npz data/member1_imu_speed.npz] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from src.data.dataset import (
    ALLOWED_INPUT_KEYS, FORBIDDEN_INPUT_PATTERNS, META_KEYS, REQUIRED_KEYS, TARGET_KEY, ImuDataset, from_arrays,
)
from src.data.windowing import SAMPLE_RATE_HZ, break_mask, session_starts


def describe_arrays(arrays: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    """Key / shape / dtype / NaN / Inf / range for every raw array."""
    rows = []
    for key, a in arrays.items():
        row: dict[str, Any] = {"key": key, "shape": list(a.shape), "dtype": str(a.dtype)}
        if a.dtype.kind in "fiu":
            f = a.astype(np.float64)
            finite = f[np.isfinite(f)]
            row.update(nan=int(np.isnan(f).sum()), inf=int(np.isinf(f).sum()),
                       min=float(finite.min()) if finite.size else None,
                       max=float(finite.max()) if finite.size else None)
        else:
            row["n_unique"] = int(len(np.unique(a)))
        rows.append(row)
    return rows


def forbidden_keys_present(keys: list[str]) -> list[str]:
    """Raw keys that look like forbidden model inputs (they may exist as target/metadata)."""
    return [k for k in keys if k not in ALLOWED_INPUT_KEYS
            and any(re.search(p, k, flags=re.IGNORECASE) for p in FORBIDDEN_INPUT_PATTERNS)]


def session_table(ds: ImuDataset, sample_rate_hz: float = SAMPLE_RATE_HZ, dt_tolerance_s: float = 0.02) -> list[dict[str, Any]]:
    starts = np.flatnonzero(session_starts(ds.session_id))
    ends = np.r_[starts[1:], len(ds)]
    brk = break_mask(ds, sample_rate_hz, dt_tolerance_s)
    rows = []
    for s, e in zip(starts, ends):
        v = ds.target[s:e]
        dt = np.diff(ds.t_session_s[s:e])
        rows.append({
            "session_id": str(ds.session_id[s]),
            "trip_id": str(ds.trip_id[s]),
            "n_samples": int(e - s),
            "duration_s": float(ds.t_session_s[e - 1] - ds.t_session_s[s]),
            "dt_median_s": float(np.median(dt)) if dt.size else None,
            "n_internal_breaks": int(brk[s + 1:e].sum()),
            "target_nan": int(np.isnan(v).sum()),
            "imu_nonfinite_rows": int((~np.isfinite(ds.imu[s:e]).all(axis=1)).sum()),
            "speed_mean_mps": float(np.nanmean(v)) if np.isfinite(v).any() else None,
            "speed_max_mps": float(np.nanmax(v)) if np.isfinite(v).any() else None,
            "stationary_frac": float(np.mean(v[np.isfinite(v)] < 0.5)) if np.isfinite(v).any() else None,
        })
    return rows


def validate(arrays: dict[str, np.ndarray], ds: ImuDataset, sample_rate_hz: float = SAMPLE_RATE_HZ,
             dt_tolerance_s: float = 0.02) -> list[str]:
    """Return hard validation errors (empty list = OK). Non-finite targets are reported, not errors."""
    errors = []
    for k in REQUIRED_KEYS:
        if k not in arrays:
            errors.append(f"missing key {k!r}")
    if ds.imu.ndim != 2 or ds.imu.shape[1] != 6:
        errors.append(f"IMU matrix must be (N, 6), got {ds.imu.shape}")
    if len(np.unique(ds.session_id)) != int(session_starts(ds.session_id).sum()):
        errors.append("session rows are not contiguous blocks")
    for sid in np.unique(ds.session_id):
        if len(np.unique(ds.trip_id[ds.session_id == sid])) != 1:
            errors.append(f"session {sid} spans multiple trips")
    dt = np.diff(ds.t_session_s)[~session_starts(ds.session_id)[1:]]
    if dt.size and abs(float(np.median(dt)) - 1.0 / sample_rate_hz) > dt_tolerance_s:
        errors.append(f"median dt {np.median(dt):.4f}s does not match {sample_rate_hz} Hz")
    if not np.isfinite(ds.imu).all():
        errors.append(f"{int((~np.isfinite(ds.imu)).sum())} non-finite IMU values")
    finite_target = ds.target[np.isfinite(ds.target)]
    if finite_target.size == 0:
        errors.append("target has no finite values")
    elif finite_target.min() < 0:
        errors.append("negative speed values in target")
    return errors


def inspect(npz_path: str | Path, sample_rate_hz: float = SAMPLE_RATE_HZ, dt_tolerance_s: float = 0.02) -> dict[str, Any]:
    with np.load(npz_path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    ds = from_arrays(arrays)
    brk = break_mask(ds, sample_rate_hz, dt_tolerance_s) & ~session_starts(ds.session_id)
    dt = np.diff(ds.t_session_s)[~session_starts(ds.session_id)[1:]]
    return {
        "npz_path": str(npz_path),
        "n_samples": len(ds),
        "arrays": describe_arrays(arrays),
        "model_input_keys": list(ALLOWED_INPUT_KEYS),
        "target_key": TARGET_KEY,
        "target_units": "m/s",
        "metadata_keys_present": [k for k in META_KEYS if k in arrays],
        "unexpected_keys": sorted(set(arrays) - set(REQUIRED_KEYS) - set(META_KEYS)),
        "forbidden_like_keys_present": forbidden_keys_present(list(arrays)),
        "n_sessions": int(len(np.unique(ds.session_id))),
        "n_trips": int(len(np.unique(ds.trip_id))),
        "sampling": {"dt_median_s": float(np.median(dt)), "dt_min_s": float(dt.min()), "dt_max_s": float(dt.max()),
                     "estimated_rate_hz": float(1.0 / np.median(dt)), "n_internal_breaks": int(brk.sum())},
        "target_nan_rows": np.flatnonzero(~np.isfinite(ds.target)).tolist(),
        "sessions": session_table(ds, sample_rate_hz, dt_tolerance_s),
        "errors": validate(arrays, ds, sample_rate_hz, dt_tolerance_s),
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"NPZ: {report['npz_path']}  samples={report['n_samples']}")
    print("\nArrays:")
    for r in report["arrays"]:
        extra = (f"nan={r['nan']} inf={r['inf']} range=[{r['min']:.4g}, {r['max']:.4g}]" if "nan" in r
                 else f"unique={r['n_unique']}")
        print(f"  {r['key']:18s} shape={str(tuple(r['shape'])):14s} dtype={r['dtype']:8s} {extra}")
    print(f"\nModel inputs: {report['model_input_keys']} -> [acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z]")
    print(f"Target: {report['target_key']} ({report['target_units']}), non-finite rows: {len(report['target_nan_rows'])}")
    print(f"Metadata (never model input): {report['metadata_keys_present']}")
    print(f"Unexpected keys: {report['unexpected_keys'] or 'none'}")
    print(f"Forbidden-like keys present in file: {report['forbidden_like_keys_present'] or 'none'}"
          " (target/metadata only, excluded from model input)")
    s = report["sampling"]
    print(f"\nSampling: median dt={s['dt_median_s']:.4f}s (~{s['estimated_rate_hz']:.2f} Hz), "
          f"dt range=[{s['dt_min_s']:.4f}, {s['dt_max_s']:.4f}], internal continuity breaks={s['n_internal_breaks']}")
    print(f"Sessions: {report['n_sessions']}  Trips: {report['n_trips']}\n")
    print(f"  {'session':12s} {'trip':6s} {'n':>7s} {'dur_s':>8s} {'breaks':>6s} {'tgtNaN':>6s} {'v_mean':>6s} {'v_max':>6s} {'stat%':>5s}")
    for r in report["sessions"]:
        print(f"  {r['session_id']:12s} {r['trip_id']:6s} {r['n_samples']:7d} {r['duration_s']:8.1f} "
              f"{r['n_internal_breaks']:6d} {r['target_nan']:6d} {r['speed_mean_mps']:6.2f} {r['speed_max_mps']:6.2f} "
              f"{100 * r['stationary_frac']:5.1f}")
    print(f"\nValidation: {'OK' if not report['errors'] else 'FAILED'}")
    for e in report["errors"]:
        print(f"  - {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--npz", default="data/member1_imu_speed.npz")
    parser.add_argument("--json", default=None, help="optional path to write the report as JSON")
    args = parser.parse_args()
    report = inspect(args.npz)
    print_report(report)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
