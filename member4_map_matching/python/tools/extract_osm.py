#!/usr/bin/env python3
"""Optional OSM extract. Requires network + osmnx. Not used at runtime."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a small drive network (OPTIONAL; needs internet/osmnx)."
    )
    parser.add_argument("--lat", type=float, default=12.9716)
    parser.add_argument("--lon", type=float, default=77.5946)
    parser.add_argument("--radius-m", type=float, default=400.0)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "small_road_network.graphml",
    )
    args = parser.parse_args()

    try:
        import osmnx as ox
    except ImportError as exc:
        raise SystemExit(
            "osmnx is not installed. Install optionally with: pip install osmnx\n"
            "Committed offline GraphML already exists for tests/runtime."
        ) from exc

    args.out.parent.mkdir(parents=True, exist_ok=True)
    graph = ox.graph_from_point(
        (args.lat, args.lon),
        dist=args.radius_m,
        network_type="drive",
    )
    ox.save_graphml(graph, args.out)
    print(f"Saved {args.out} nodes={len(graph.nodes)} edges={len(graph.edges)}")


if __name__ == "__main__":
    main()
