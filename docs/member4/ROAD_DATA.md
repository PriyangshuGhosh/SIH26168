# Member 4 road data

Visual tiles (any map SDK) are **not** the road graph.

## Source

- **OpenStreetMap** via Overpass (`python/sih26168_map_matching/osm_overpass.py`)
- License: **ODbL 1.0** — © OpenStreetMap contributors
- Runtime matching: **local `.roadpack` only** (no HTTP)

## New region

```bash
# Offline from committed GraphML/GeoJSON
python3 member4_map_matching/python/tools/install_region.py \
  --source member4_map_matching/data/small_road_network.graphml \
  --catalog member4_map_matching/data/maps

# Optional live Overpass (needs network). Radius capped (default max 2500 m).
python3 member4_map_matching/python/tools/extract_osm.py \
  --lat 12.9716 --lon 77.5946 --radius-m 400 \
  --catalog /path/to/writable/catalog
```

Region ids come from WGS84 bounds (`r_<minlat>_<minlon>_...`), not city names.

## Layout

```text
catalog/
  manifest.json
  regions/<region_id>.roadpack
  tmp/                 # incomplete downloads; never the active pack
```

Install is write-tmp → validate → `os.replace` → atomic manifest replace.

## Match-time coverage

No covering region → `OUTSIDE_MAP` / `NO_MAP_DATA`. Unsnapped lat/lon preserved. Not `0,0`.
