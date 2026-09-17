#!/usr/bin/env python3
"""SYNTHETIC accuracy: HMM vs independent nearest-road baseline.

Labels are synthetic ground-truth on the deterministic grid — not field GNSS.
"""

from __future__ import annotations

import argparse
import json
import sys
from math import cos, pi, radians
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sih26168_map_matching.geometry import haversine_m  # noqa: E402
from sih26168_map_matching.map_matcher import MapMatcher  # noqa: E402
from sih26168_map_matching.road_graph import build_synthetic_grid  # noqa: E402
from sih26168_map_matching.types import NavigationState  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "results" / "accuracy_synthetic.json",
    )
    args = parser.parse_args()

    network = build_synthetic_grid(blocks=3, spacing_m=80.0)
    matcher = MapMatcher(network)

    # True path: eastbound along southernmost horizontal corridor with noise.
    lat0, lon0 = 12.9716, 77.5946
    dlon = 5.0 / (111_320.0 * cos(radians(lat0)))
    noise_lon = 12.0 / (111_320.0 * cos(radians(lat0)))
    truth = []
    noisy = []
    for i in range(40):
        lat_t = lat0
        lon_t = lon0 + i * dlon
        truth.append((lat_t, lon_t))
        # Add lateral noise toward a parallel road to stress nearest-road
        sign = 1.0 if (i // 5) % 2 == 0 else -1.0
        noisy.append(
            NavigationState(
                timestamp=float(i),
                latitude=lat_t + sign * 0.0,
                longitude=lon_t + sign * noise_lon * 0.15,
                yaw_rad=pi / 2,  # east
                position_cov_m2=((16.0, 0.0), (0.0, 16.0)),
            )
        )

    # Inject a brief parallel-road confusion spike
    for i in range(15, 22):
        noisy[i].latitude = lat0 + 80.0 / 111_320.0  # jump toward next east-west road
        noisy[i].position_cov_m2 = ((36.0, 0.0), (0.0, 36.0))

    hmm = matcher.match_trajectory(noisy)
    base = matcher.nearest_road_baseline(noisy)

    def mean_err(outputs):
        errs = [
            haversine_m(o.lat_snapped, o.lon_snapped, t[0], t[1])
            for o, t in zip(outputs, truth)
            if o.is_on_road_network
        ]
        return sum(errs) / len(errs) if errs else float("nan")

    report = {
        "dataset": "SYNTHETIC_GRID",
        "note": "Not real-world OSM / GNSS accuracy. Parallel-road spike injected.",
        "n": len(noisy),
        "hmm_mean_error_m_on_road": mean_err(hmm),
        "nearest_mean_error_m_on_road": mean_err(base),
        "hmm_on_road_fraction": sum(1 for o in hmm if o.is_on_road_network) / len(hmm),
        "nearest_on_road_fraction": sum(1 for o in base if o.is_on_road_network)
        / len(base),
        "hmm_mean_confidence": sum(o.confidence_score for o in hmm) / len(hmm),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
