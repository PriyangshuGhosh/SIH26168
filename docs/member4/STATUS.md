# Member 4 status

## Checklist (gate audit)

| Item | Status |
|---|---|
| OSM extraction / preprocessing | IMPLEMENTED — `python/tools/extract_osm.py` (optional network); committed offline `data/small_road_network.graphml` |
| Offline road graph | IMPLEMENTED+TESTED — GraphML / GeoJSON / `.roadpack` / SQLite loaders + synthetic grid |
| Spatial index / R-tree | IMPLEMENTED+TESTED — SQLite R*Tree (Python) + in-memory AABB (Python/C++); parity test |
| Candidate generation | IMPLEMENTED+TESTED — uncertainty-aware radius + distance filter |
| Emission probability | IMPLEMENTED+TESTED — log-Gaussian distance / heading |
| Transition probability | IMPLEMENTED+TESTED — network vs observed displacement + heading |
| Sliding-window Viterbi | IMPLEMENTED+TESTED — online window + batch trajectory decode |
| Confidence score | IMPLEMENTED+TESTED — softmax over candidates; uncertainty softening |
| On-road / off-road status | IMPLEMENTED+TESTED — fail-safe pass-through when weak |
| Deterministic test dataset | IMPLEMENTED+TESTED — synthetic grid + GraphML fixture |
| Accuracy benchmark | IMPLEMENTED+TESTED — **SYNTHETIC VALIDATION ONLY** (`evaluate_accuracy.py`) |
| Runtime benchmark | IMPLEMENTED+TESTED (desktop Python/C++); **ANDROID PERFORMANCE: NOT VALIDATED** |
| Python reference | IMPLEMENTED+TESTED — `sih26168_map_matching` package |
| C++ runtime | IMPLEMENTED+TESTED — `MapMatchingEngine` + roadpack loader |
| Member 3 integration | IMPLEMENTED+TESTED — consumes `member3::NavigationState` (C++ include + Python mirror) |
| Member 5/6 output interface | IMPLEMENTED (types/docs); wiring in Member 5 still `StubMapMatcher` until Member 5 swaps engine |
| Documentation | IMPLEMENTED — README, ALGORITHM, INTEGRATION, STATUS |

## Limitations

- Field GNSS/OSM accuracy not claimed; synthetic accuracy is labeled **SYNTHETIC VALIDATION ONLY**.
- Android/NDK latency not measured in this workspace.
- Member 5 still uses `StubMapMatcher` until Member 5 wires `MapMatchingEngine`.
- Committed OSM extract is a small demo tile, not city-scale coverage.
