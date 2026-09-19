"""Provision/install/select Member 4 roadpacks. No HTTP on the match path."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .osm_overpass import (
    OSM_ATTRIBUTION,
    OSM_LICENSE,
    OSM_SOURCE,
    download_overpass_xml,
    parse_osm_xml,
)
from .region import (
    MapRegion,
    bbox_from_point,
    find_covering,
    load_manifest,
    region_id_from_bounds,
    utc_now_iso,
)
from .road_graph import load_network, write_roadpack
from .roadpack_validate import validate_roadpack


class DownloadState(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    VALIDATING = "validating"
    INSTALLING = "installing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RoadDataError(Exception):
    pass


def safe_relative_path(rel: str) -> bool:
    if not rel or rel.startswith("/") or rel.startswith("\\"):
        return False
    if "://" in rel or (len(rel) >= 2 and rel[1] == ":"):
        return False
    parts = Path(rel.replace("\\", "/")).parts
    if parts.count("..") > 1:
        return False
    if ".." in parts and parts[0] != "..":
        return False
    return True


@dataclass
class RoadDataConfig:
    prefetch_radius_m: float = 400.0
    max_prefetch_radius_m: float = 2500.0
    boundary_prefetch_m: float = 80.0
    max_storage_bytes: int = 64 * 1024 * 1024
    max_region_count: int = 8
    max_roadpack_bytes: int = 32 * 1024 * 1024


@dataclass
class RoadDataManager:
    root: Path
    config: RoadDataConfig = field(default_factory=RoadDataConfig)
    fetcher: object | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _states: dict[str, DownloadState] = field(default_factory=dict, init=False)
    _errors: dict[str, str] = field(default_factory=dict, init=False)
    _progress: dict[str, float] = field(default_factory=dict, init=False)
    _cancel: set[str] = field(default_factory=set, init=False)
    _active_id: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "regions").mkdir(exist_ok=True)
        (self.root / "tmp").mkdir(exist_ok=True)
        if not self.manifest_path.exists():
            self._write_manifest({"version": 2, "coordinate_reference": "EPSG:4326", "regions": []})

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def get_available_regions(self) -> list[MapRegion]:
        _, regions = load_manifest(self.manifest_path)
        return regions

    def get_active_region(self) -> MapRegion | None:
        regions = {r.region_id: r for r in self.get_available_regions()}
        return regions.get(self._active_id) if self._active_id else None

    def get_download_state(self, region_id: str | None = None) -> dict:
        with self._lock:
            if region_id:
                return {
                    "region_id": region_id,
                    "state": self._states.get(region_id, DownloadState.IDLE).value,
                    "error": self._errors.get(region_id, ""),
                    "progress": self._progress.get(region_id, 0.0),
                }
            return {
                rid: {
                    "state": st.value,
                    "error": self._errors.get(rid, ""),
                    "progress": self._progress.get(rid, 0.0),
                }
                for rid, st in self._states.items()
            }

    def storage_info(self) -> dict:
        regions = self.get_available_regions()
        used = 0
        for r in regions:
            p = self._abs_pack(r.roadpack_path)
            if p.is_file():
                used += p.stat().st_size
        return {
            "used_bytes": used,
            "max_bytes": self.config.max_storage_bytes,
            "remaining_bytes": max(0, self.config.max_storage_bytes - used),
            "region_count": len(regions),
            "max_region_count": self.config.max_region_count,
            "active_region_id": self._active_id,
        }

    def is_region_available(self, lat: float, lon: float) -> bool:
        return find_covering(self.get_available_regions(), lat, lon) is not None

    def select_region_for_location(self, lat: float, lon: float) -> MapRegion | None:
        hit = find_covering(self.get_available_regions(), lat, lon)
        if hit is None:
            self._active_id = None
            return None
        hit.last_used_at = utc_now_iso()
        self._active_id = hit.region_id
        self._upsert_region(hit)
        return hit

    def cancel_download(self, region_id: str) -> None:
        with self._lock:
            self._cancel.add(region_id)
            self._states[region_id] = DownloadState.CANCELLED

    def delete_region(self, region_id: str) -> None:
        if region_id == self._active_id:
            raise RoadDataError("cannot delete active region")
        regions = [r for r in self.get_available_regions() if r.region_id != region_id]
        leftover = next((r for r in self.get_available_regions() if r.region_id == region_id), None)
        if leftover:
            pack = self._abs_pack(leftover.roadpack_path)
            if pack.is_file():
                pack.unlink()
            meta = Path(str(pack) + ".meta.json")
            if meta.is_file():
                meta.unlink()
        self._write_regions(regions)

    def prefetch_around(self, lat: float, lon: float, radius_m: float | None = None) -> str:
        radius = min(radius_m or self.config.prefetch_radius_m, self.config.max_prefetch_radius_m)
        existing = self.select_region_for_location(lat, lon)
        if existing is not None:
            if existing.approaching_boundary(lat, lon, self.config.boundary_prefetch_m):
                return self._prefetch_neighbors(existing)
            return existing.region_id
        return self.download_bbox(*bbox_from_point(lat, lon, radius), synthetic=False)

    def _prefetch_neighbors(self, active: MapRegion) -> str:
        last_id = active.region_id
        for bbox in active.neighbor_bboxes():
            if find_covering(self.get_available_regions(), (bbox[0] + bbox[1]) / 2, (bbox[2] + bbox[3]) / 2):
                continue
            last_id = self.download_bbox(*bbox, synthetic=False)
        return last_id

    def download_region(self, region_id: str) -> str:
        r = next((x for x in self.get_available_regions() if x.region_id == region_id), None)
        if r is None:
            raise RoadDataError("unknown region_id")
        return self.download_bbox(
            r.min_latitude, r.max_latitude, r.min_longitude, r.max_longitude, synthetic=r.synthetic
        )

    def install_local_source(
        self,
        source_path: Path,
        *,
        synthetic: bool,
        source: str,
        license_name: str,
        attribution: str,
    ) -> MapRegion:
        network = load_network(Path(source_path))
        bounds = network.bounds()
        if bounds is None:
            raise RoadDataError("source has no geometry")
        min_lat, max_lat, min_lon, max_lon = bounds
        rid = region_id_from_bounds(min_lat, max_lat, min_lon, max_lon)
        return self._install_network(
            network,
            rid,
            min_lat,
            max_lat,
            min_lon,
            max_lon,
            synthetic=synthetic,
            source=source,
            license_name=license_name,
            attribution=attribution,
        )

    def download_bbox(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        *,
        synthetic: bool = False,
    ) -> str:
        rid = region_id_from_bounds(min_lat, max_lat, min_lon, max_lon)
        with self._lock:
            if rid in self._cancel:
                self._cancel.discard(rid)
            self._states[rid] = DownloadState.DOWNLOADING
            self._progress[rid] = 0.1
            self._errors.pop(rid, None)
        try:
            if rid in self._cancel:
                raise RoadDataError("cancelled")
            xml = self._fetch_xml(min_lat, max_lat, min_lon, max_lon)
            with self._lock:
                self._states[rid] = DownloadState.VALIDATING
                self._progress[rid] = 0.5
            network = parse_osm_xml(xml)
            region = self._install_network(
                network,
                rid,
                min_lat,
                max_lat,
                min_lon,
                max_lon,
                synthetic=synthetic,
                source=OSM_SOURCE,
                license_name=OSM_LICENSE,
                attribution=OSM_ATTRIBUTION,
            )
            with self._lock:
                self._states[rid] = DownloadState.READY
                self._progress[rid] = 1.0
            return region.region_id
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._states[rid] = DownloadState.FAILED
                self._errors[rid] = str(exc)
            raise

    def _fetch_xml(self, min_lat, max_lat, min_lon, max_lon) -> bytes:
        if self.fetcher is not None:
            return self.fetcher(min_lat, max_lat, min_lon, max_lon)
        return download_overpass_xml(min_lat, max_lat, min_lon, max_lon)

    def _install_network(
        self,
        network,
        rid: str,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        *,
        synthetic: bool,
        source: str,
        license_name: str,
        attribution: str,
    ) -> MapRegion:
        tmp_dir = self.root / "tmp"
        tmp_dir.mkdir(exist_ok=True)
        tmp = tmp_dir / f"{uuid.uuid4().hex}.roadpack"
        try:
            write_roadpack(network, tmp)
            check = validate_roadpack(tmp, max_bytes=self.config.max_roadpack_bytes)
            if not check.ok:
                raise RoadDataError(check.error)
            dest_rel = f"regions/{rid}.roadpack"
            if not safe_relative_path(dest_rel):
                raise RoadDataError("unsafe path")
            dest = self.root / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)
            region = MapRegion(
                region_id=rid,
                min_latitude=min_lat,
                max_latitude=max_lat,
                min_longitude=min_lon,
                max_longitude=max_lon,
                roadpack_path=dest_rel.replace("\\", "/"),
                source=source,
                license=license_name,
                checksum=check.checksum_sha256,
                created_at=utc_now_iso(),
                downloaded_at=utc_now_iso(),
                last_used_at=utc_now_iso(),
                bytes=check.bytes,
                node_count=check.node_count,
                edge_count=check.edge_count,
                synthetic=synthetic,
                attribution=attribution,
            )
            self._enforce_storage(keep_id=rid)
            self._upsert_region(region)
            return region
        finally:
            if tmp.exists():
                tmp.unlink()

    def _abs_pack(self, rel_or_abs: str) -> Path:
        p = Path(rel_or_abs)
        return p if p.is_absolute() else (self.root / p)

    def _upsert_region(self, region: MapRegion) -> None:
        regions = [r for r in self.get_available_regions() if r.region_id != region.region_id]
        regions.append(region)
        self._write_regions(regions)

    def _enforce_storage(self, keep_id: str) -> None:
        regions = self.get_available_regions()
        def size_of(r: MapRegion) -> int:
            p = self._abs_pack(r.roadpack_path)
            return p.stat().st_size if p.is_file() else r.bytes

        regions.sort(key=lambda r: r.last_used_at or r.downloaded_at or r.created_at)
        while len(regions) >= self.config.max_region_count:
            victim = next((r for r in regions if r.region_id not in {keep_id, self._active_id}), None)
            if victim is None:
                break
            self._purge_files(victim)
            regions = [r for r in regions if r.region_id != victim.region_id]
        used = sum(size_of(r) for r in regions)
        while used > self.config.max_storage_bytes:
            victim = next((r for r in regions if r.region_id not in {keep_id, self._active_id}), None)
            if victim is None:
                break
            used -= size_of(victim)
            self._purge_files(victim)
            regions = [r for r in regions if r.region_id != victim.region_id]
        self._write_regions(regions)

    def _purge_files(self, region: MapRegion) -> None:
        p = self._abs_pack(region.roadpack_path)
        if p.is_file():
            p.unlink()

    def _write_regions(self, regions: list[MapRegion]) -> None:
        header, _ = load_manifest(self.manifest_path) if self.manifest_path.exists() else ({}, [])
        header["version"] = 2
        header["coordinate_reference"] = "EPSG:4326"
        header["regions"] = [r.to_manifest_obj() for r in regions]
        self._write_manifest(header)

    def _write_manifest(self, data: dict) -> None:
        fd, tmp = tempfile.mkstemp(prefix="manifest.", suffix=".json", dir=str(self.root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, self.manifest_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
