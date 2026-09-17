# Member 4 status

## Checklist

| Item | Status |
|---|---|
| Target-area OSM data extracted | IMPLEMENTED+TESTED — committed `data/small_road_network.graphml` (~400 m, 12.9716, 77.5946); regenerate via optional `extract_osm.py` |
| Offline road graph built | IMPLEMENTED+TESTED — GraphML/GeoJSON/roadpack loaders + synthetic grid |
| R-tree/spatial index built | IMPLEMENTED+TESTED — SQLite R-tree (Python) + in-memory AABB index with deterministic parity test |
| Candidate generation | IMPLEMENTED+TESTED — uncertainty-aware radius + heading-tolerant scoring |
| Emission probability | IMPLEMENTED+TESTED — documented log-Gaussian distance/heading |
| Transition probability | IMPLEMENTED+TESTED — network vs observed displacement + turn term |
| Viterbi sliding window | IMPLEMENTED+TESTED — online window + batch trajectory decode |
| Confidence/on-road status | IMPLEMENTED+TESTED — softmax confidence; fail-safe pass-through |
| Offline deterministic test set | IMPLEMENTED+TESTED — synthetic grid fixtures + GraphML |
| Accuracy/runtime benchmark | IMPLEMENTED+TESTED (desktop); **ANDROID PERFORMANCE: NOT VALIDATED** |
| Interface handed to Members 5/6 | IMPLEMENTED+TESTED — docs/member4/INTEGRATION.md + headers |

## Limitations

- Field GNSS/OSM accuracy not claimed; synthetic accuracy is labeled SYNTHETIC.
- Android/NDK latency not measured in this workspace.
- Member 5 still uses `StubMapMatcher` until Member 5 wires `MapMatchingEngine`.
- Committed OSM extract is a small demo tile, not city-scale coverage.
