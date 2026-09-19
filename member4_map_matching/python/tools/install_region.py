#!/usr/bin/env python3
"""Install a local GraphML/GeoJSON/roadpack into a multi-region catalog. Offline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sih26168_map_matching.road_data_manager import RoadDataManager  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--source-name", default="OpenStreetMap")
    p.add_argument("--license", default="ODbL-1.0")
    p.add_argument("--attribution", default="© OpenStreetMap contributors")
    args = p.parse_args()
    mgr = RoadDataManager(args.catalog)
    region = mgr.install_local_source(
        args.source,
        synthetic=args.synthetic,
        source=args.source_name,
        license_name=args.license,
        attribution=args.attribution,
    )
    print(
        f"installed id={region.region_id} edges={region.edge_count} "
        f"nodes={region.node_count} bytes={region.bytes} synthetic={region.synthetic}"
    )


if __name__ == "__main__":
    main()
