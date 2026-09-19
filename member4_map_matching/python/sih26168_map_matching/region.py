"""Geographic region records. IDs are bound-derived, never city names."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def region_id_from_bounds(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float
) -> str:
    def fmt(x: float) -> str:
        return f"{x:.5f}".replace("-", "m").replace(".", "p")

    return f"r_{fmt(min_lat)}_{fmt(min_lon)}_{fmt(max_lat)}_{fmt(max_lon)}"


def bbox_from_point(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


@dataclass
class MapRegion:
    region_id: str
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float
    roadpack_path: str
    version: str = "1"
    source: str = ""
    license: str = ""
    checksum: str = ""
    created_at: str = ""
    downloaded_at: str = ""
    last_used_at: str = ""
    bytes: int = 0
    node_count: int = 0
    edge_count: int = 0
    synthetic: bool = False
    attribution: str = ""

    def contains(self, lat: float, lon: float) -> bool:
        if not math.isfinite(lat) or not math.isfinite(lon):
            return False
        return (
            self.min_latitude <= lat <= self.max_latitude
            and self.min_longitude <= lon <= self.max_longitude
        )

    def area_deg2(self) -> float:
        return max(0.0, self.max_latitude - self.min_latitude) * max(
            0.0, self.max_longitude - self.min_longitude
        )

    def signed_distance_to_boundary_m(self, lat: float, lon: float) -> float:
        dlat_n = (self.max_latitude - lat) * 111320.0
        dlat_s = (lat - self.min_latitude) * 111320.0
        coslat = max(math.cos(math.radians(lat)), 1e-6)
        dlon_e = (self.max_longitude - lon) * 111320.0 * coslat
        dlon_w = (lon - self.min_longitude) * 111320.0 * coslat
        if not self.contains(lat, lon):
            return -min(abs(dlat_n), abs(dlat_s), abs(dlon_e), abs(dlon_w))
        return min(dlat_n, dlat_s, dlon_e, dlon_w)

    def approaching_boundary(self, lat: float, lon: float, threshold_m: float) -> bool:
        d = self.signed_distance_to_boundary_m(lat, lon)
        return 0.0 <= d <= threshold_m

    def neighbor_bboxes(self) -> list[tuple[float, float, float, float]]:
        dlat = self.max_latitude - self.min_latitude
        dlon = self.max_longitude - self.min_longitude
        return [
            (
                self.min_latitude + dy * dlat,
                self.max_latitude + dy * dlat,
                self.min_longitude + dx * dlon,
                self.max_longitude + dx * dlon,
            )
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        ]

    def to_manifest_obj(self) -> dict:
        return {
            "id": self.region_id,
            "roadpack": self.roadpack_path,
            "min_lat": self.min_latitude,
            "max_lat": self.max_latitude,
            "min_lon": self.min_longitude,
            "max_lon": self.max_longitude,
            "road_count": self.edge_count,
            "node_count": self.node_count,
            "version": self.version,
            "source": self.source,
            "license": self.license,
            "checksum_sha256": self.checksum,
            "created_at": self.created_at,
            "downloaded_at": self.downloaded_at,
            "last_used_at": self.last_used_at,
            "bytes": self.bytes,
            "synthetic": self.synthetic,
            "attribution": self.attribution,
            "coordinate_reference": "EPSG:4326",
        }

    @classmethod
    def from_manifest_obj(cls, obj: dict) -> "MapRegion":
        return cls(
            region_id=str(obj["id"]),
            min_latitude=float(obj["min_lat"]),
            max_latitude=float(obj["max_lat"]),
            min_longitude=float(obj["min_lon"]),
            max_longitude=float(obj["max_lon"]),
            roadpack_path=str(obj["roadpack"]),
            version=str(obj.get("version", "1")),
            source=str(obj.get("source", "")),
            license=str(obj.get("license", "")),
            checksum=str(obj.get("checksum_sha256", obj.get("checksum", ""))),
            created_at=str(obj.get("created_at", obj.get("built_at", ""))),
            downloaded_at=str(obj.get("downloaded_at", "")),
            last_used_at=str(obj.get("last_used_at", "")),
            bytes=int(obj.get("bytes", 0) or 0),
            node_count=int(obj.get("node_count", 0) or 0),
            edge_count=int(obj.get("road_count", obj.get("edge_count", 0)) or 0),
            synthetic=bool(obj.get("synthetic", False)),
            attribution=str(obj.get("attribution", "")),
        )


def load_manifest(path: Path) -> tuple[dict, list[MapRegion]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    regions = [MapRegion.from_manifest_obj(o) for o in data.get("regions", [])]
    return data, regions


def find_covering(regions: list[MapRegion], lat: float, lon: float) -> MapRegion | None:
    hits = [r for r in regions if r.contains(lat, lon)]
    if not hits:
        return None
    return min(hits, key=lambda r: r.area_deg2())
