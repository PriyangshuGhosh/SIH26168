# Member 4 — Offline HMM Map Matching

Projects noisy Member 3 `NavigationState` samples onto an offline road network
using spatial candidate generation + HMM Viterbi (sliding window).

Road **matching** data is `.roadpack`. Visual map tiles are a different system.

## Layout

```text
member4_map_matching/
├── python/sih26168_map_matching/   # HMM + RoadDataManager
├── python/tools/                   # extract/install/build
├── cpp/                            # MapMatchingEngine + RegionCatalog
├── data/maps/                      # catalog + regions
├── android/                        # Member 6 API contract
└── tests/python/
```

## Quick start (offline)

```bash
python3 -m pip install -r member4_map_matching/requirements.txt
python3 member4_map_matching/python/tools/build_synthetic_graph.py
python3 member4_map_matching/python/tools/install_region.py \
  --source member4_map_matching/data/small_road_network.graphml \
  --catalog member4_map_matching/data/maps
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target member4_cpp_tests member4_benchmark
ctest --test-dir build -R member4 --output-on-failure
PYTHONPATH=member4_map_matching/python python3 -m pytest member4_map_matching/tests/python -q
```

Match path never downloads OSM. Provisioning uses Overpass (ODbL) or a local GraphML file.

See [docs/member4/ROAD_DATA.md](../docs/member4/ROAD_DATA.md).
