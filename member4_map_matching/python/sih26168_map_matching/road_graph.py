"""Road graph + portable offline formats (GeoJSON / GraphML / roadpack / SQLite)."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import networkx as nx
from shapely.geometry import LineString, shape
from shapely import wkt as shapely_wkt

from .geometry import bearing_rad, haversine_m


@dataclass
class RoadSegment:
    segment_id: int
    label: str
    geometry: LineString
    length_m: float
    heading_rad: float
    u_node: int
    v_node: int
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


@dataclass
class RoadNetwork:
    segments: dict[int, RoadSegment] = field(default_factory=dict)
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    node_coords: dict[int, tuple[float, float]] = field(default_factory=dict)

    def add_segment(self, segment: RoadSegment) -> None:
        self.segments[segment.segment_id] = segment
        if not self.graph.has_node(segment.u_node):
            self.graph.add_node(segment.u_node)
        if not self.graph.has_node(segment.v_node):
            self.graph.add_node(segment.v_node)
        self.graph.add_edge(
            segment.u_node,
            segment.v_node,
            weight=segment.length_m,
            segment_id=segment.segment_id,
        )


def _segment_from_linestring(
    segment_id: int,
    label: str,
    geometry: LineString,
    u_node: int,
    v_node: int,
    length_m: float | None = None,
) -> RoadSegment:
    coords = list(geometry.coords)
    if len(coords) < 2:
        raise ValueError(f"segment {label} needs >= 2 coordinates")
    lon0, lat0 = coords[0]
    lon1, lat1 = coords[-1]
    if length_m is None:
        length_m = 0.0
        for (a_lon, a_lat), (b_lon, b_lat) in zip(coords[:-1], coords[1:]):
            length_m += haversine_m(a_lat, a_lon, b_lat, b_lon)
    heading = bearing_rad(lat0, lon0, lat1, lon1)
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    return RoadSegment(
        segment_id=segment_id,
        label=label,
        geometry=geometry,
        length_m=float(length_m),
        heading_rad=heading,
        u_node=u_node,
        v_node=v_node,
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
    )


def load_geojson(path: Path) -> RoadNetwork:
    data = json.loads(path.read_text(encoding="utf-8"))
    network = RoadNetwork()
    next_node = 0
    node_index: dict[tuple[float, float], int] = {}

    def node_id(lon: float, lat: float) -> int:
        nonlocal next_node
        key = (round(lon, 7), round(lat, 7))
        if key not in node_index:
            node_index[key] = next_node
            network.node_coords[next_node] = (lat, lon)
            next_node += 1
        return node_index[key]

    for idx, feature in enumerate(data["features"]):
        geom = shape(feature["geometry"])
        if geom.geom_type != "LineString":
            continue
        props = feature.get("properties") or {}
        coords = list(geom.coords)
        u = int(props.get("u", node_id(*coords[0])))
        v = int(props.get("v", node_id(*coords[-1])))
        if u not in network.node_coords:
            network.node_coords[u] = (coords[0][1], coords[0][0])
        if v not in network.node_coords:
            network.node_coords[v] = (coords[-1][1], coords[-1][0])
        seg_id = int(props.get("id", idx + 1))
        label = str(props.get("name", f"{u}->{v}"))
        length = props.get("length_m")
        network.add_segment(
            _segment_from_linestring(
                seg_id, label, geom, u, v, float(length) if length is not None else None
            )
        )
    return network


def load_graphml(path: Path) -> RoadNetwork:
    """Load OSMnx-style GraphML without requiring osmnx at runtime."""
    graph = nx.read_graphml(path)
    # OSMnx stores nodes as strings; edges may be MultiDiGraph.
    if not isinstance(graph, (nx.DiGraph, nx.MultiDiGraph)):
        graph = nx.DiGraph(graph)

    network = RoadNetwork()
    node_map: dict[str, int] = {}
    for i, (nid, data) in enumerate(graph.nodes(data=True)):
        node_map[str(nid)] = i
        network.node_coords[i] = (float(data["y"]), float(data["x"]))

    seg_id = 1
    edges = graph.edges(keys=True, data=True) if graph.is_multigraph() else (
        (u, v, 0, d) for u, v, d in graph.edges(data=True)
    )
    for u, v, key, data in edges:
        geom = None
        if "geometry" in data and data["geometry"]:
            raw = data["geometry"]
            if isinstance(raw, str):
                geom = shapely_wkt.loads(raw)
            else:
                geom = raw
        if geom is None:
            lat_u, lon_u = network.node_coords[node_map[str(u)]]
            lat_v, lon_v = network.node_coords[node_map[str(v)]]
            geom = LineString([(lon_u, lat_u), (lon_v, lat_v)])
        length = data.get("length")
        label = f"{u}->{v}:{key}"
        network.add_segment(
            _segment_from_linestring(
                seg_id,
                label,
                geom,
                node_map[str(u)],
                node_map[str(v)],
                float(length) if length is not None else None,
            )
        )
        seg_id += 1
    return network


def load_network(path: Path) -> RoadNetwork:
    suffix = path.suffix.lower()
    if suffix == ".geojson":
        return load_geojson(path)
    if suffix in {".graphml", ".xml"}:
        return load_graphml(path)
    if suffix == ".roadpack":
        return load_roadpack(path)
    raise ValueError(f"unsupported network format: {path}")


def write_roadpack(network: RoadNetwork, path: Path) -> None:
    """Portable text format for C++ runtime (no SQLite dependency)."""
    lines = ["SIH26168_ROADPACK_V1", f"NUM_NODES {len(network.node_coords)}"]
    for nid in sorted(network.node_coords):
        lat, lon = network.node_coords[nid]
        lines.append(f"NODE {nid} {lat:.8f} {lon:.8f}")
    lines.append(f"NUM_SEGMENTS {len(network.segments)}")
    for sid in sorted(network.segments):
        seg = network.segments[sid]
        coords = list(seg.geometry.coords)
        lines.append(
            "SEG "
            f"{seg.segment_id} {seg.u_node} {seg.v_node} "
            f"{seg.length_m:.6f} {seg.heading_rad:.8f} {len(coords)}"
        )
        # label may contain spaces — store on next line after marker
        lines.append(f"LABEL {seg.label}")
        for lon, lat in coords:
            lines.append(f"PT {lat:.8f} {lon:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_roadpack(path: Path) -> RoadNetwork:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "SIH26168_ROADPACK_V1":
        raise ValueError("invalid roadpack header")
    network = RoadNetwork()
    i = 1
    while i < len(lines):
        parts = lines[i].split()
        if not parts:
            i += 1
            continue
        if parts[0] == "NODE":
            nid = int(parts[1])
            network.node_coords[nid] = (float(parts[2]), float(parts[3]))
            i += 1
        elif parts[0] == "SEG":
            seg_id = int(parts[1])
            u, v = int(parts[2]), int(parts[3])
            length_m = float(parts[4])
            heading = float(parts[5])
            n_pts = int(parts[6])
            i += 1
            label = lines[i][6:] if lines[i].startswith("LABEL ") else f"{u}->{v}"
            i += 1
            pts = []
            for _ in range(n_pts):
                p = lines[i].split()
                pts.append((float(p[2]), float(p[1])))  # lon, lat
                i += 1
            geom = LineString(pts)
            seg = _segment_from_linestring(seg_id, label, geom, u, v, length_m)
            seg.heading_rad = heading
            network.add_segment(seg)
        else:
            i += 1
    return network


def write_sqlite(network: RoadNetwork, path: Path) -> None:
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE roads (
                id INTEGER PRIMARY KEY,
                road_segment_id INTEGER UNIQUE NOT NULL,
                label TEXT NOT NULL,
                geometry_wkt TEXT NOT NULL,
                length_m REAL NOT NULL,
                heading_rad REAL NOT NULL,
                u_node INTEGER NOT NULL,
                v_node INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE road_index USING rtree(
                id, min_longitude, max_longitude, min_latitude, max_latitude
            )
            """
        )
        for seg in network.segments.values():
            conn.execute(
                """
                INSERT INTO roads (
                    id, road_segment_id, label, geometry_wkt, length_m,
                    heading_rad, u_node, v_node
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seg.segment_id,
                    seg.segment_id,
                    seg.label,
                    seg.geometry.wkt,
                    seg.length_m,
                    seg.heading_rad,
                    seg.u_node,
                    seg.v_node,
                ),
            )
            conn.execute(
                """
                INSERT INTO road_index (
                    id, min_longitude, max_longitude, min_latitude, max_latitude
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (seg.segment_id, seg.min_lon, seg.max_lon, seg.min_lat, seg.max_lat),
            )


def query_sqlite_bbox(
    path: Path,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> list[int]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            SELECT id FROM road_index
            WHERE min_longitude <= ? AND max_longitude >= ?
              AND min_latitude <= ? AND max_latitude >= ?
            """,
            (max_lon, min_lon, max_lat, min_lat),
        ).fetchall()
    return [int(r[0]) for r in rows]


def network_distance_m(
    network: RoadNetwork,
    from_candidate_u_v: tuple[int, int],
    to_candidate_u_v: tuple[int, int],
    same_segment: bool,
    observed_distance_m: float,
) -> float:
    """Approximate on-network travel between candidate endpoints."""
    if same_segment:
        return max(observed_distance_m, 0.0)
    _, prev_v = from_candidate_u_v
    curr_u, _ = to_candidate_u_v
    if prev_v == curr_u:
        return max(observed_distance_m, 0.0)
    try:
        return float(
            nx.shortest_path_length(
                network.graph, source=prev_v, target=curr_u, weight="weight"
            )
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return math.inf


def build_synthetic_grid(
    origin_lat: float = 12.971600,
    origin_lon: float = 77.594600,
    blocks: int = 3,
    spacing_m: float = 80.0,
) -> RoadNetwork:
    """Deterministic grid for offline unit/HMM tests (not real OSM coverage)."""
    # metres to deg near origin
    dlat = spacing_m / 111_320.0
    dlon = spacing_m / (111_320.0 * math.cos(math.radians(origin_lat)))
    network = RoadNetwork()
    # nodes (r,c) -> id
    def nid(r: int, c: int) -> int:
        return r * (blocks + 1) + c

    for r in range(blocks + 1):
        for c in range(blocks + 1):
            network.node_coords[nid(r, c)] = (
                origin_lat + r * dlat,
                origin_lon + c * dlon,
            )

    seg_id = 1
    # horizontal edges eastbound + westbound
    for r in range(blocks + 1):
        for c in range(blocks):
            u, v = nid(r, c), nid(r, c + 1)
            lat_u, lon_u = network.node_coords[u]
            lat_v, lon_v = network.node_coords[v]
            geom = LineString([(lon_u, lat_u), (lon_v, lat_v)])
            network.add_segment(
                _segment_from_linestring(seg_id, f"H{r}_{c}_E", geom, u, v, spacing_m)
            )
            seg_id += 1
            geom_b = LineString([(lon_v, lat_v), (lon_u, lat_u)])
            network.add_segment(
                _segment_from_linestring(seg_id, f"H{r}_{c}_W", geom_b, v, u, spacing_m)
            )
            seg_id += 1
    # vertical edges northbound + southbound
    for r in range(blocks):
        for c in range(blocks + 1):
            u, v = nid(r, c), nid(r + 1, c)
            lat_u, lon_u = network.node_coords[u]
            lat_v, lon_v = network.node_coords[v]
            geom = LineString([(lon_u, lat_u), (lon_v, lat_v)])
            network.add_segment(
                _segment_from_linestring(seg_id, f"V{r}_{c}_N", geom, u, v, spacing_m)
            )
            seg_id += 1
            geom_b = LineString([(lon_v, lat_v), (lon_u, lat_u)])
            network.add_segment(
                _segment_from_linestring(seg_id, f"V{r}_{c}_S", geom_b, v, u, spacing_m)
            )
            seg_id += 1
    return network


def write_geojson(network: RoadNetwork, path: Path) -> None:
    features = []
    for seg in network.segments.values():
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": seg.segment_id,
                    "name": seg.label,
                    "u": seg.u_node,
                    "v": seg.v_node,
                    "length_m": seg.length_m,
                    "heading_rad": seg.heading_rad,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(c) for c in seg.geometry.coords],
                },
            }
        )
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )
