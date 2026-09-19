# Member 4 status

## Gate audit

| Item | Status |
|---|---|
| HMM matcher (existing) | VALIDATED (synthetic + committed OSM extract, host tests) |
| Real OSM GraphML → roadpack | VALIDATED (offline install of `small_road_network.graphml`) |
| Live Overpass download | NOT VALIDATED (API exists; no live fetch recorded this run) |
| Multi-region catalog | VALIDATED (unit tests + `data/maps/manifest.json`) |
| Location-based select | VALIDATED (smallest covering bbox) |
| Atomic install / failed download | VALIDATED (Python tests; mocked HTTP) |
| Storage LRU | VALIDATED (unit test) |
| Boundary prefetch logic | PARTIAL (neighbor bbox enqueue; no driving trace) |
| Offline match after install | VALIDATED (fetcher disabled after install) |
| OUTSIDE_MAP / no 0,0 snap | VALIDATED |
| Member 5 ABI fields 1–7 | VALIDATED (unchanged order) |
| Extra match status fields | VALIDATED (C++/Python; Member 5 does not copy them yet) |
| Android RoadDataManager wiring | NOT VALIDATED (contract only) |
| Real driving GNSS traces | NOT VALIDATED |
| Android/NDK latency | NOT VALIDATED |

## REAL DRIVING VALIDATION: NOT VALIDATED

## Limitations

- Committed OSM extract is a small tile (~80 edges), not city-scale.
- `osm_downloader.py` no longer hardcodes a city; old root-level scripts that called OSMnx download on import are gone.
- Member 6 visual map SDK is out of scope here.
