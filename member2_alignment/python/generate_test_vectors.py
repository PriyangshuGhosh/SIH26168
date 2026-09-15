#!/usr/bin/env python3
"""Regenerate deterministic Member 2 synthetic test vectors.

Usage (from repository root):

    PYTHONPATH=member2_alignment/python python3 member2_alignment/python/generate_test_vectors.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sih26168_alignment.frame_aligner import FrameAligner
from sih26168_alignment.simulator import SEED, all_scenario_names, generate_scenario, write_scenario_csv
from sih26168_alignment.types import OptionalGnssAid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "data" / "generated"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    index = {"seed": SEED, "scenarios": []}
    for name in all_scenario_names():
        sc = generate_scenario(name, rng=np.random.default_rng(SEED))
        csv_path = OUT / f"{name}.csv"
        write_scenario_csv(str(csv_path), sc)
        al = FrameAligner()
        last = None
        for i in range(sc.t.size):
            if sc.gnss_speed is not None and np.isfinite(sc.gnss_speed[i]):
                al.feed_gnss(
                    OptionalGnssAid(
                        timestamp=float(sc.t[i]),
                        speed_mps=float(sc.gnss_speed[i]),
                        hdop=float(sc.gnss_hdop[i]),
                        num_sats=int(sc.gnss_sats[i]),
                    )
                )
            last = al.process(
                float(sc.t[i]),
                *[float(x) for x in sc.acc_p[i]],
                *[float(x) for x in sc.gyro_p[i]],
            )
        index["scenarios"].append(
            {
                "name": name,
                "csv": str(csv_path.relative_to(ROOT)),
                "samples": int(sc.t.size),
                "notes": sc.notes,
                "final_status": int(last.status) if last else None,
                "final_confidence": last.confidence.overall if last else None,
            }
        )
    (OUT / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {len(index['scenarios'])} scenarios to {OUT}")


if __name__ == "__main__":
    main()
