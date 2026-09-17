#!/usr/bin/env python3
"""Build deterministic synthetic road grid (offline; not real OSM coverage)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sih26168_map_matching.road_graph import (  # noqa: E402
    build_synthetic_grid,
    write_geojson,
    write_roadpack,
    write_sqlite,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data")
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--spacing-m", type=float, default=80.0)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    network = build_synthetic_grid(blocks=args.blocks, spacing_m=args.spacing_m)
    geojson = args.out_dir / "synthetic_grid.geojson"
    roadpack = args.out_dir / "synthetic_grid.roadpack"
    sqlite = args.out_dir / "synthetic_grid.sqlite"
    write_geojson(network, geojson)
    write_roadpack(network, roadpack)
    write_sqlite(network, sqlite)
    print(f"segments={len(network.segments)} geojson={geojson} roadpack={roadpack}")


if __name__ == "__main__":
    main()
