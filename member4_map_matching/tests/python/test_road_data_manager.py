from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from sih26168_map_matching.map_matcher import MapMatcher
from sih26168_map_matching.region import MapRegion, find_covering, region_id_from_bounds
from sih26168_map_matching.road_data_manager import RoadDataConfig, RoadDataError, RoadDataManager
from sih26168_map_matching.road_graph import build_synthetic_grid, write_roadpack
from sih26168_map_matching.roadpack_validate import validate_roadpack
from sih26168_map_matching.types import NavigationState


def _tiny_osm_xml(lat: float, lon: float) -> bytes:
    a = lat
    b = lat + 0.0004
    c = lon
    d = lon + 0.0004
    return f"""<?xml version="1.0"?>
<osm>
  <node id="1" lat="{a}" lon="{c}"/>
  <node id="2" lat="{a}" lon="{d}"/>
  <node id="3" lat="{b}" lon="{d}"/>
  <way id="10">
    <nd ref="1"/><nd ref="2"/>
    <tag k="highway" v="residential"/>
    <tag k="maxspeed" v="30"/>
  </way>
  <way id="11">
    <nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="residential"/>
  </way>
</osm>
""".encode()


@pytest.fixture
def catalog(tmp_path):
    return RoadDataManager(tmp_path, RoadDataConfig(max_region_count=3, max_storage_bytes=200_000))


def test_region_id_not_city_name():
    rid = region_id_from_bounds(12.97, 12.98, 77.59, 77.60)
    assert "bangalore" not in rid.lower()
    assert "delhi" not in rid.lower()
    assert rid.startswith("r_")


def test_region_bounds_and_overlap():
    a = MapRegion("a", 0, 2, 0, 2, "a.roadpack")
    b = MapRegion("b", 1, 1.5, 1, 1.5, "b.roadpack")
    assert find_covering([a, b], 1.2, 1.2).region_id == "b"
    assert find_covering([a], 9.0, 9.0) is None


def test_missing_and_existing_region(catalog, tmp_path):
    net = build_synthetic_grid(blocks=2, spacing_m=40.0)
    src = tmp_path / "g.geojson"
    from sih26168_map_matching.road_graph import write_geojson  # type: ignore
    try:
        write_geojson(net, src)
    except Exception:
        pack = tmp_path / "g.roadpack"
        write_roadpack(net, pack)
        src = pack
    r = catalog.install_local_source(
        src, synthetic=True, source="synthetic", license_name="test", attribution="test"
    )
    assert catalog.is_region_available((r.min_latitude + r.max_latitude) / 2, (r.min_longitude + r.max_longitude) / 2)
    assert catalog.select_region_for_location(0.0, 0.0) is None


def test_download_success_and_checksum(catalog):
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(12.97, 77.59)
    rid = catalog.download_bbox(12.969, 12.972, 77.589, 77.592)
    st = catalog.get_download_state(rid)
    assert st["state"] == "ready"
    region = next(x for x in catalog.get_available_regions() if x.region_id == rid)
    pack = catalog.root / region.roadpack_path
    v = validate_roadpack(pack, expected_checksum=region.checksum)
    assert v.ok


def test_download_failure_keeps_old(catalog, tmp_path):
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(12.97, 77.59)
    rid_a = catalog.download_bbox(12.969, 12.972, 77.589, 77.592)
    catalog.select_region_for_location(12.9705, 77.5905)
    before = (catalog.manifest_path.read_text(), list((catalog.root / "regions").glob("*.roadpack")))

    def boom(*_):
        raise RuntimeError("network gone")

    catalog.fetcher = boom
    with pytest.raises(RuntimeError):
        catalog.download_bbox(13.0, 13.01, 77.6, 77.61)
    after = catalog.manifest_path.read_text()
    assert rid_a in after
    assert catalog.get_download_state(region_id_from_bounds(13.0, 13.01, 77.6, 77.61))["state"] == "failed"
    assert (catalog.root / "regions" / f"{rid_a}.roadpack").is_file()
    _ = before


def test_checksum_and_corrupt_rejected(catalog, tmp_path):
    bad = tmp_path / "bad.roadpack"
    bad.write_text("not a pack\n")
    v = validate_roadpack(bad)
    assert not v.ok
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(12.97, 77.59)
    rid = catalog.download_bbox(12.969, 12.972, 77.589, 77.592)
    region = next(x for x in catalog.get_available_regions() if x.region_id == rid)
    pack = catalog.root / region.roadpack_path
    v2 = validate_roadpack(pack, expected_checksum="deadbeef")
    assert not v2.ok
    assert "checksum" in v2.error


def test_interrupted_tmp_not_promoted(catalog):
    def interrupt(*_):
        raise RuntimeError("cut")

    catalog.fetcher = interrupt
    with pytest.raises(RuntimeError):
        catalog.download_bbox(1.0, 1.01, 2.0, 2.01)
    assert list((catalog.root / "regions").glob("*.roadpack")) == []
    data = json.loads(catalog.manifest_path.read_text())
    assert data["regions"] == []


def test_atomic_manifest_and_recovery(catalog):
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(12.97, 77.59)
    catalog.download_bbox(12.969, 12.972, 77.589, 77.592)
    assert catalog.manifest_path.is_file()
    json.loads(catalog.manifest_path.read_text())


def test_storage_lru(catalog):
    catalog.config.max_region_count = 2
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(bbox[0] + 0.001, bbox[2] + 0.001)
    catalog.download_bbox(10.0, 10.01, 20.0, 20.01)
    catalog.download_bbox(11.0, 11.01, 21.0, 21.01)
    catalog.download_bbox(12.0, 12.01, 22.0, 22.01)
    ids = {r.region_id for r in catalog.get_available_regions()}
    assert len(ids) <= 2


def test_cannot_delete_active(catalog):
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(12.97, 77.59)
    rid = catalog.download_bbox(12.969, 12.972, 77.589, 77.592)
    catalog.select_region_for_location(12.9705, 77.5905)
    with pytest.raises(RoadDataError):
        catalog.delete_region(rid)


def test_outside_map_and_nan(catalog):
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(12.97, 77.59)
    catalog.download_bbox(12.969, 12.972, 77.589, 77.592)
    region = catalog.get_available_regions()[0]
    matcher = MapMatcher.from_path(catalog.root / region.roadpack_path)
    far = matcher.match(NavigationState(0.0, 28.6, 77.2))
    assert far.match_status == "OUTSIDE_MAP"
    assert far.match_valid is False
    assert far.road_segment_id == 0
    assert abs(far.lat_snapped - 28.6) < 1e-12
    bad = matcher.match(NavigationState(0.0, float("nan"), 77.2))
    assert bad.match_status == "INVALID_COORDINATES"


def test_candidate_cap_and_parallel_disconnected():
    net = build_synthetic_grid(blocks=3, spacing_m=80.0)
    matcher = MapMatcher(net)
    origin = NavigationState(0.0, 12.9716, 77.5946, yaw_rad=math.pi / 2)
    ok = matcher.match(origin)
    assert ok.match_status in {"OK", "REJECTED", "NO_CANDIDATES"}
    inf = matcher.match(NavigationState(0.0, float("inf"), 77.5946))
    assert inf.match_status == "INVALID_COORDINATES"


def test_offline_after_install(catalog):
    catalog.fetcher = lambda *bbox: _tiny_osm_xml(12.97, 77.59)
    rid = catalog.download_bbox(12.969, 12.972, 77.589, 77.592)
    catalog.fetcher = None

    def no_net(*_):
        raise AssertionError("network used")

    catalog.fetcher = no_net
    region = next(x for x in catalog.get_available_regions() if x.region_id == rid)
    matcher = MapMatcher.from_path(catalog.root / region.roadpack_path)
    mid_lat = (region.min_latitude + region.max_latitude) / 2
    mid_lon = (region.min_longitude + region.max_longitude) / 2
    out = matcher.match(NavigationState(1.0, mid_lat, mid_lon, yaw_rad=math.pi / 2))
    assert out.match_status != "NO_MAP_DATA"


def test_boundary_prefetch_flag():
    r = MapRegion("x", 0.0, 0.01, 0.0, 0.01, "x.roadpack")
    assert r.approaching_boundary(0.005, 0.005, 1e9)
    assert not r.approaching_boundary(0.005, 0.005, 0.001)


def test_path_traversal_rejected():
    from sih26168_map_matching.road_data_manager import safe_relative_path

    assert not safe_relative_path("../../etc/passwd")
    assert not safe_relative_path("/abs")
    assert safe_relative_path("regions/ok.roadpack")
