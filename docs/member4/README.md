# Member 4 — Offline HMM Map Matching

## Current completion status

**Status: IMPLEMENTED + HOST VALIDATED; field and Android validation remain open.**

### Confirmed in the repository

- HMM/Viterbi map matching is implemented with candidate generation, emission/transition scoring, and offline road-network matching.
- Committed OSM extract → roadpack conversion is validated.
- Multi-region map catalog and location-based selection are validated by tests.
- Atomic install / failed-download handling and storage LRU are validated.
- Offline matching works after installation without a live map fetch.
- OUTSIDE_MAP handling avoids falling back to a `0,0` snap.
- The Member 5 ABI fields remain compatible.
- The latest host CTest run passed Member 4 C++ tests and the benchmark.

### Validation boundary

- Boundary prefetch is **PARTIAL**: neighbor-bbox enqueue exists, but no driving trace validates it.
- Android RoadDataManager wiring is **NOT VALIDATED**.
- Real-driving GNSS traces are **NOT VALIDATED**.
- Android/NDK latency is **NOT VALIDATED**.
- The committed OSM extract is a small synthetic/demo-scale dataset, not city-scale coverage.

## Documentation

- [Algorithm](ALGORITHM.md)
- [Integration](INTEGRATION.md)
- [Road data](ROAD_DATA.md)
- [Detailed status](STATUS.md)
- [Runtime build/run](../../member4_map_matching/README.md)
