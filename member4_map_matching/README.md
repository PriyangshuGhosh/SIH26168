# Member 4 — Offline HMM Map Matching

Projects noisy Member 3 `NavigationState` samples onto an offline road network
using spatial candidate generation + HMM Viterbi (sliding window).

## Layout

```text
member4_map_matching/
├── python/sih26168_map_matching/   # reference HMM
├── python/tools/                   # OSM extract (optional), DB/roadpack builders, bench
├── cpp/                            # MapMatchingEngine runtime
├── data/                           # offline fixtures (GraphML + generated synthetic)
├── tests/python/
└── docs via ../../docs/member4/
```

## Quick start (offline)

```bash
python3 -m pip install -r member4_map_matching/requirements.txt
python3 member4_map_matching/python/tools/build_synthetic_graph.py
python3 member4_map_matching/python/tools/build_road_database.py \
  --graphml member4_map_matching/data/small_road_network.graphml

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target member4_cpp_tests member4_benchmark
ctest --test-dir build -R member4 --output-on-failure

PYTHONPATH=member4_map_matching/python python3 -m pytest member4_map_matching/tests/python -q
python3 member4_map_matching/python/tools/benchmark.py
python3 member4_map_matching/python/tools/evaluate_accuracy.py
```

Runtime **never** downloads OSM. The optional `extract_osm.py` tool is for regenerating the committed GraphML when network is available.

## Output contract

See [docs/member4/INTEGRATION.md](../docs/member4/INTEGRATION.md).
