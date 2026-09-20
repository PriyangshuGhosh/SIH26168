"""Recover real GPS/GNSS position ground truth for the test-split trips from the OFFICIAL IO-VNBD
source repository (https://github.com/onyekpeu/IO-VNBD, git-lfs, branch "master"), and align it
row-for-row to the existing derived training dataset (`data/member1_imu_speed.npz`).

Why this exists: `data/member1_imu_speed.npz` (this repo's only committed training data) was
confirmed by inspection to contain NO position/GPS fields at all -- only accelerometer, gyroscope,
a supervised speed target, and session/trip grouping. The OFFICIAL IO-VNBD smartphone recordings
(`.../Categorised IOVNB Dataset/<driver>/<trip>/S-<trip>.csv`) *do* contain
`GPS LATITUDE/LONGITUDE/ALTITUDE/SPEED/ACCURACY/SATELLITES` alongside the same accelerometer/
gyroscope columns -- confirmed by downloading and inspecting the real files (git-lfs objects, not
the tiny pointer blobs the plain GitHub API/raw endpoints return; fetched via
media.githubusercontent.com). This script recovers that GPS data for genuine navigation-benchmark
ground truth. It NEVER modifies `data/member1_imu_speed.npz` (opened read-only) and NEVER feeds any
recovered GPS field into an M1 training or inference input -- see `docs/data_protocol.md`'s
existing (unchanged) `ALLOWED_INPUT_KEYS`/leakage guard, which this script does not touch.

Alignment method (verified, not assumed): each trip's raw accelerometer column is cross-correlated
against the corresponding npz session's `acc` column over a small integer row-offset search; the
offset with the lowest mean absolute error is kept only if that error is below a strict threshold
(confirms real, exact correspondence -- both files store the same underlying recording). A session
that cannot be confidently aligned is skipped and reported, never guessed.

Usage:
    python scripts/recover_iovnbd_gnss.py --raw-dir <dir with downloaded S-<trip>.csv files> \\
        --out data/derived/gnss_reference.npz
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# trip_id (matches data/member1_imu_speed.npz's trip_id / session_id prefix) -> raw file name
TEST_SPLIT_TRIPS = {
    "S1": "S-S1.csv", "S2": "S-S2.csv", "S3a": "S-S3a.csv",
    "S3b": "S-S3b.csv", "S3c": "S-S3c.csv", "S4": "S-S4.csv",
}

SOURCE_REPO = "https://github.com/onyekpeu/IO-VNBD (branch: master, git-lfs)"
SOURCE_PATH_TEMPLATE = (
    "Synchronised V abd S datasets/Categorised IOVNB Dataset/S (Driver A)/{trip}/S-{trip}.csv"
)

ALIGN_SEARCH_RANGE = range(-2000, 50000, 1)
ALIGN_MAX_MAE = 0.5  # m/s^2; real match (see docs/gru_velocity.md) is ~0.06, misalignment is >>1
ALIGN_PROBE_ROWS = 2000


def load_raw_csv(path: Path) -> dict[str, np.ndarray]:
    with open(path, newline="", encoding="latin-1") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        rows = list(reader)
    idx = {name: header.index(name) for name in [
        "GPS LATITUDE (degrees)", "GPS LONGITUDE (degrees)", "GPS ALTITUDE (m)",
        "GPS SPEED (Kmh)", "GPS ACCURACY (m)", "GPS SATELLITES IN RANGE",
        "TIME SINCE START (ms)",
    ]}
    acc_idx = [i for i, h in enumerate(header) if h.startswith("ACCELEROMETER")]
    if len(acc_idx) != 3:
        raise ValueError(f"expected 3 ACCELEROMETER columns, found {len(acc_idx)} in {path}")

    def col(name: str, cast=float) -> np.ndarray:
        j = idx[name]
        out = np.empty(len(rows))
        for i, r in enumerate(rows):
            try:
                out[i] = cast(r[j])
            except ValueError:
                out[i] = np.nan
        return out

    sats = []
    for r in rows:
        raw = r[idx["GPS SATELLITES IN RANGE"]]
        try:
            # "18 / 19" style value in this dataset: in-view/in-use: keep the first number.
            sats.append(float(str(raw).split("/")[0].strip()))
        except ValueError:
            sats.append(np.nan)

    acc = np.array([[float(r[j]) for j in acc_idx] for r in rows], dtype=np.float64)
    return {
        "acc": acc,
        "lat": col("GPS LATITUDE (degrees)"),
        "lon": col("GPS LONGITUDE (degrees)"),
        "alt": col("GPS ALTITUDE (m)"),
        "gps_speed_mps": col("GPS SPEED (Kmh)") / 3.6,
        "gps_accuracy_m": col("GPS ACCURACY (m)"),
        "gps_sats": np.array(sats),
        "t_ms": col("TIME SINCE START (ms)"),
    }


def find_alignment(npz_acc: np.ndarray, raw_acc: np.ndarray) -> tuple[int, float]:
    """Returns (offset, mae) such that npz_acc[i] ~= raw_acc[i + offset]. Brute-force search over a
    small integer range -- exact, not a guess, and self-verifying via the MAE threshold check by
    the caller."""
    best_off, best_err = 0, float("inf")
    n_probe = min(ALIGN_PROBE_ROWS, len(npz_acc), len(raw_acc))
    for off in ALIGN_SEARCH_RANGE:
        if off >= 0:
            a, b = npz_acc[:n_probe], raw_acc[off:off + n_probe]
        else:
            a, b = npz_acc[-off:-off + n_probe], raw_acc[:n_probe]
        n = min(len(a), len(b))
        if n < 200:
            continue
        err = float(np.mean(np.abs(a[:n] - b[:n])))
        if err < best_err:
            best_off, best_err = off, err
    return best_off, best_err


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--npz", default=str(ROOT / "data" / "member1_imu_speed.npz"))
    p.add_argument("--raw-dir", required=True, help="directory containing the downloaded S-<trip>.csv files")
    p.add_argument("--out", default=str(ROOT / "data" / "derived" / "gnss_reference.npz"))
    args = p.parse_args()

    npz_path = Path(args.npz)
    d = np.load(npz_path, allow_pickle=True)  # read-only open; never written back to
    session_id = d["session_id"]
    trip_id = d["trip_id"]
    acc = d["acc"].astype(np.float64)
    t_session_s = d["t_session_s"]

    raw_dir = Path(args.raw_dir)
    recovered: dict[str, Any] = {}
    report_lines = []
    for trip, fname in TEST_SPLIT_TRIPS.items():
        raw_path = raw_dir / fname
        if not raw_path.exists():
            report_lines.append(f"{trip}: SKIPPED (raw file not found at {raw_path})")
            continue
        raw = load_raw_csv(raw_path)

        # A trip_id can span multiple npz sessions (an internal recording break -> separate
        # sessions, e.g. S2__s00 + S2__s01); align and export each session block independently.
        trip_mask = trip_id == trip
        sessions_for_trip = sorted(set(session_id[trip_mask].tolist()))
        for sess in sessions_for_trip:
            smask = session_id == sess
            npz_acc_sess = acc[smask]
            offset, mae = find_alignment(npz_acc_sess, raw["acc"])
            if mae > ALIGN_MAX_MAE:
                report_lines.append(
                    f"{sess}: SKIPPED (best alignment offset={offset} still has MAE={mae:.3f} "
                    f"m/s^2 > {ALIGN_MAX_MAE} threshold -- not a confident match, not exported)")
                continue
            n = int(smask.sum())
            lo, hi = offset, offset + n
            if lo < 0 or hi > len(raw["lat"]):
                report_lines.append(
                    f"{sess}: SKIPPED (aligned window [{lo},{hi}) falls outside raw file of "
                    f"length {len(raw['lat'])})")
                continue
            recovered[f"{sess}/session_id"] = np.full(n, sess)
            recovered[f"{sess}/npz_row_offset"] = np.flatnonzero(smask)
            recovered[f"{sess}/lat"] = raw["lat"][lo:hi]
            recovered[f"{sess}/lon"] = raw["lon"][lo:hi]
            recovered[f"{sess}/alt_m"] = raw["alt"][lo:hi]
            recovered[f"{sess}/gps_speed_mps"] = raw["gps_speed_mps"][lo:hi]
            recovered[f"{sess}/gps_accuracy_m"] = raw["gps_accuracy_m"][lo:hi]
            recovered[f"{sess}/gps_sats"] = raw["gps_sats"][lo:hi]
            recovered[f"{sess}/alignment_offset"] = offset
            recovered[f"{sess}/alignment_mae_mps2"] = mae
            report_lines.append(
                f"{sess}: RECOVERED n={n} rows, alignment offset={offset}, "
                f"accel-match MAE={mae:.4f} m/s^2, "
                f"gps_fix_frac={float(np.mean(np.isfinite(raw['lat'][lo:hi]))):.3f}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    recovered["_provenance_source_repo"] = SOURCE_REPO
    recovered["_provenance_note"] = (
        "GPS/GNSS reference ONLY. Never used as an M1 model input -- see docs/data_protocol.md's "
        "unchanged ALLOWED_INPUT_KEYS leakage guard. data/member1_imu_speed.npz was opened "
        "read-only and is byte-for-byte unmodified by this script."
    )
    np.savez_compressed(out_path, **recovered)
    print(f"Wrote {out_path}")
    print("\n".join(report_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
