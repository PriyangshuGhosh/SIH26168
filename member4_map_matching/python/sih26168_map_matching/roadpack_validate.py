"""Validate untrusted .roadpack files. No execution, no network."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from .road_graph import load_roadpack


@dataclass
class ValidationResult:
    ok: bool
    error: str = ""
    node_count: int = 0
    edge_count: int = 0
    bytes: int = 0
    checksum_sha256: str = ""
    min_lat: float = 0.0
    max_lat: float = 0.0
    min_lon: float = 0.0
    max_lon: float = 0.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_roadpack(
    path: Path,
    *,
    expected_checksum: str | None = None,
    max_bytes: int = 64 * 1024 * 1024,
) -> ValidationResult:
    if not path.is_file():
        return ValidationResult(False, "roadpack missing")
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        return ValidationResult(False, "roadpack size rejected", bytes=size)
    header = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if not header or header[0].strip() != "SIH26168_ROADPACK_V1":
        return ValidationResult(False, "invalid roadpack header", bytes=size)
    digest = sha256_file(path)
    if expected_checksum and digest.lower() != expected_checksum.lower():
        return ValidationResult(False, "checksum mismatch", bytes=size, checksum_sha256=digest)
    try:
        network = load_roadpack(path)
    except Exception as exc:  # noqa: BLE001 — treat any parse error as invalid input
        return ValidationResult(False, f"schema/parse error: {exc}", bytes=size, checksum_sha256=digest)
    if not network.segments or not network.node_coords:
        return ValidationResult(False, "empty graph", bytes=size, checksum_sha256=digest)
    bounds = network.bounds()
    if bounds is None:
        return ValidationResult(False, "missing bounds", bytes=size, checksum_sha256=digest)
    min_lat, max_lat, min_lon, max_lon = bounds
    for lat, lon in network.node_coords.values():
        if not math.isfinite(lat) or not math.isfinite(lon):
            return ValidationResult(False, "NaN/Inf coordinate", bytes=size, checksum_sha256=digest)
        if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
            return ValidationResult(False, "coordinate out of range", bytes=size, checksum_sha256=digest)
    connected = network.graph.number_of_edges()
    if connected <= 0:
        return ValidationResult(False, "no connectivity", bytes=size, checksum_sha256=digest)
    return ValidationResult(
        True,
        node_count=len(network.node_coords),
        edge_count=len(network.segments),
        bytes=size,
        checksum_sha256=digest,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )
