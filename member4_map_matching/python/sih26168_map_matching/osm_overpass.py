"""OpenStreetMap Overpass client (ODbL). Optional network. Not used at match time."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from urllib.error import URLError
from urllib.request import Request, urlopen

from shapely.geometry import LineString

from .road_graph import RoadNetwork, _segment_from_linestring

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_LICENSE = "ODbL-1.0"
OSM_SOURCE = "OpenStreetMap"
OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL 1.0)"
DRIVE_HIGHWAYS = (
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
)


def bbox_query(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> str:
    hw = "|".join(DRIVE_HIGHWAYS)
    return (
        "[out:xml][timeout:25];"
        f'way["highway"~"^({hw})$"]({min_lat:.7f},{min_lon:.7f},{max_lat:.7f},{max_lon:.7f});'
        "(._;>;);out body;"
    )


def download_overpass_xml(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    *,
    opener=None,
    timeout_s: float = 30.0,
) -> bytes:
    q = bbox_query(min_lat, max_lat, min_lon, max_lon)
    body = q.encode("utf-8")
    if opener is not None:
        return opener(body)
    req = Request(OVERPASS_URL, data=body, method="POST", headers={"User-Agent": "SIH26168-member4/1.0"})
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — Overpass HTTPS, documented
            return resp.read()
    except URLError as exc:
        raise RuntimeError(f"overpass download failed: {exc}") from exc


def parse_osm_xml(xml_bytes: bytes) -> RoadNetwork:
    root = ET.fromstring(xml_bytes)
    nodes: dict[str, tuple[float, float]] = {}
    for node in root.findall("node"):
        nid = node.get("id")
        lat = node.get("lat")
        lon = node.get("lon")
        if nid is None or lat is None or lon is None:
            continue
        la, lo = float(lat), float(lon)
        if not math.isfinite(la) or not math.isfinite(lo):
            continue
        nodes[nid] = (la, lo)

    network = RoadNetwork()
    node_index: dict[str, int] = {}
    next_id = 0

    def nid_int(osm_id: str, lat: float, lon: float) -> int:
        nonlocal next_id
        if osm_id not in node_index:
            node_index[osm_id] = next_id
            network.node_coords[next_id] = (lat, lon)
            next_id += 1
        return node_index[osm_id]

    seg_id = 1
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        highway = tags.get("highway") or ""
        if highway not in DRIVE_HIGHWAYS:
            continue
        refs = [nd.get("ref") for nd in way.findall("nd") if nd.get("ref") in nodes]
        if len(refs) < 2:
            continue
        coords = []
        for ref in refs:
            lat, lon = nodes[ref]
            coords.append((lon, lat))
            nid_int(ref, lat, lon)
        geom = LineString(coords)
        u = nid_int(refs[0], *nodes[refs[0]])
        v = nid_int(refs[-1], *nodes[refs[-1]])
        maxspeed_kmh = None
        if tags.get("maxspeed"):
            try:
                maxspeed_kmh = float(str(tags["maxspeed"]).split()[0])
            except ValueError:
                maxspeed_kmh = None
        oneway = str(tags.get("oneway", "no")).lower() in {"yes", "true", "1"}
        seg = _segment_from_linestring(seg_id, highway or f"way-{seg_id}", geom, u, v)
        seg.highway = highway
        seg.maxspeed_kmh = maxspeed_kmh
        seg.oneway = oneway if oneway else True
        network.add_segment(seg)
        seg_id += 1
        if not oneway:
            rev = LineString(list(reversed(coords)))
            rseg = _segment_from_linestring(seg_id, highway or f"way-{seg_id}", rev, v, u)
            rseg.highway = highway
            rseg.maxspeed_kmh = maxspeed_kmh
            rseg.oneway = False
            network.add_segment(rseg)
            seg_id += 1
    return network
