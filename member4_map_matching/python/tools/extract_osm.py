#!/usr/bin/env python3
"""Optional OSM extract via Overpass. Caps radius. Never used at match time."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sih26168_map_matching.osm_overpass import download_overpass_xml, parse_osm_xml  # noqa: E402
from sih26168_map_matching.region import bbox_from_point  # noqa: E402
from sih26168_map_matching.road_graph import write_roadpack  # noqa: E402
from sih26168_map_matching.road_data_manager import RoadDataManager  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius-m", type=float, default=400.0)
    parser.add_argument("--max-radius-m", type=float, default=2500.0)
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--out-roadpack", type=Path, default=None)
    args = parser.parse_args()
    radius = min(args.radius_m, args.max_radius_m)
    bbox = bbox_from_point(args.lat, args.lon, radius)
    if args.catalog is not None:
        mgr = RoadDataManager(args.catalog)
        rid = mgr.download_bbox(*bbox)
        print(f"installed {rid}")
        return
    xml = download_overpass_xml(*bbox)
    net = parse_osm_xml(xml)
    out = args.out_roadpack or Path("extracted.roadpack")
    write_roadpack(net, out)
    print(f"wrote {out} segments={len(net.segments)}")


if __name__ == "__main__":
    main()
