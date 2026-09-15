#!/usr/bin/env python3
"""Recorded-IMU validation entry point.

No suitable recorded IMU traces are currently committed in this repository.
This script documents the expected CSV schema and, if a file is provided,
runs FrameAligner and writes a summary. It does not invent real-world
accuracy numbers.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sih26168_alignment.frame_aligner import FrameAligner  # noqa: E402
from sih26168_alignment.types import OptionalGnssAid  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "csv",
        nargs="?",
        help="CSV with columns t,ax_p,ay_p,az_p,gx_p,gy_p,gz_p[,speed,hdop,sats]",
    )
    args = p.parse_args()
    if not args.csv:
        print(
            "NOT VALIDATED on recorded data: no IMU recording is in the repository.\n"
            "Expected units: timestamp seconds, accel m/s^2 (specific force), gyro rad/s.\n"
            "Place a file under member2_alignment/tests/data/recorded/ and rerun:\n"
            "  PYTHONPATH=member2_alignment/python python3 "
            "member2_alignment/python/validate_recorded.py path.csv"
        )
        return 0
    path = Path(args.csv)
    al = FrameAligner()
    n = 0
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            t = float(row["t"])
            if "gnss_speed" in row and row["gnss_speed"] not in ("", "nan"):
                try:
                    al.feed_gnss(
                        OptionalGnssAid(
                            timestamp=t,
                            speed_mps=float(row["gnss_speed"]),
                            hdop=float(row.get("gnss_hdop", 1.2) or 1.2),
                            num_sats=int(float(row.get("gnss_sats", 10) or 10)),
                        )
                    )
                except ValueError:
                    pass
            last = al.process(
                t,
                float(row["ax_p"]),
                float(row["ay_p"]),
                float(row["az_p"]),
                float(row["gx_p"]),
                float(row["gy_p"]),
                float(row["gz_p"]),
            )
            n += 1
    print(f"processed {n} samples")
    print(f"final_status {int(last.status)} {last.status.name}")
    print(f"final_confidence {last.confidence.overall:.4f}")
    print(f"q_pv {last.q_pv.tolist()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
