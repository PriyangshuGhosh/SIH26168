#!/usr/bin/env python3
"""Latency benchmark for Python map matcher (desktop). ANDROID: NOT VALIDATED."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from math import cos, radians
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sih26168_map_matching.map_matcher import MapMatcher  # noqa: E402
from sih26168_map_matching.road_graph import build_synthetic_grid  # noqa: E402
from sih26168_map_matching.types import NavigationState  # noqa: E402


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def make_trajectory(n: int = 200) -> list[NavigationState]:
    lat0, lon0 = 12.9716, 77.5946
    dlat = 8.0 / 111_320.0
    states = []
    for i in range(n):
        states.append(
            NavigationState(
                timestamp=float(i),
                latitude=lat0 + i * dlat,
                longitude=lon0 + 3.0 / (111_320.0 * cos(radians(lat0))),
                yaw_rad=0.0,
                position_cov_m2=((25.0, 0.0), (0.0, 25.0)),
            )
        )
    return states


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "results" / "runtime_python.json",
    )
    args = parser.parse_args()

    matcher = MapMatcher(build_synthetic_grid())
    states = make_trajectory(args.steps)
    # warmup
    for s in states[:10]:
        matcher.match(s)
    matcher.reset()

    samples_ms: list[float] = []
    for s in states:
        t0 = time.perf_counter()
        matcher.match(s)
        samples_ms.append((time.perf_counter() - t0) * 1000.0)

    samples_ms.sort()
    report = {
        "platform": "desktop_python",
        "android_performance": "NOT_VALIDATED",
        "n": len(samples_ms),
        "mean_ms": statistics.fmean(samples_ms),
        "p50_ms": percentile(samples_ms, 50),
        "p95_ms": percentile(samples_ms, 95),
        "p99_ms": percentile(samples_ms, 99),
        "max_ms": samples_ms[-1],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
