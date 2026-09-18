#!/usr/bin/env python3
"""Build SQLite R-tree DB + roadpack from GraphML/GeoJSON (offline)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sih26168_map_matching.road_graph import (  # noqa: E402
    load_network,
    write_roadpack,
    write_sqlite,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graphml", type=Path, default=None)
    parser.add_argument("--geojson", type=Path, default=None)
    parser.add_argument("--out-prefix", type=Path, default=None)
    args = parser.parse_args()

    src = args.graphml or args.geojson
    if src is None:
        default = Path(__file__).resolve().parents[2] / "data" / "small_road_network.graphml"
        src = default
    if not src.exists():
        raise SystemExit(f"missing map source: {src}")

    network = load_network(src)
    prefix = args.out_prefix or src.with_suffix("")
    sqlite_path = Path(str(prefix) + ".sqlite")
    roadpack_path = Path(str(prefix) + ".roadpack")
    write_sqlite(network, sqlite_path)
    write_roadpack(network, roadpack_path)
    print(
        f"Indexed {len(network.segments)} segments -> {sqlite_path} , {roadpack_path}"
    )


if __name__ == "__main__":
    main()
