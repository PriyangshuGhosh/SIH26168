# SIH26168

Repository for the SIH26168 intelligent GNSS-denied navigation system.

## Differentiator: Vision + Depth

We are investigating a **confidence-aware visual-inertial-depth layer** as an additional sensing modality during GNSS outages. Camera-derived scene geometry and visual motion will be fused with the existing IMU + AI speed + EKF pipeline, with automatic confidence gating and fallback when vision is unreliable.

See the design and experimental plan: **[docs/VISION_DEPTH_DIFFERENTIATOR.md](docs/VISION_DEPTH_DIFFERENTIATOR.md)**

> Monocular depth is not treated as a direct metric localization solution because of scale ambiguity. The goal is to combine visual geometry/motion with IMU and vehicle constraints and prove improvement experimentally.

## Team Work Distribution & Deliverables

The complete production-grade work distribution, interface contracts, module dependencies, integration gates, engineering rules, and deliverables are maintained in:

**[docs/WORK_DISTRIBUTION.md](docs/WORK_DISTRIBUTION.md)**

### Baseline Pipeline

`Phone IMU/GNSS → Frame Alignment → AI Speed Estimation → EKF/UKF Fusion → Offline HMM Map Matching → Native C++ Engine → Mobile Navigation UI`

### Enhanced Experimental Pipeline

`Phone Camera → Depth/Visual Motion → Confidence → EKF/UKF Fusion`

The enhanced path is auxiliary: if camera quality is poor or the vision module fails, navigation falls back to the baseline IMU + AI-speed + map pipeline.

### Integration Order

**Member 2 → Member 1 → Member 3 → Member 4 → Member 5 → Member 6**

The vision/depth track is integrated experimentally across Members 3, 5, and 6 after the baseline pipeline is stable.

## Member 2 (frame alignment)

Implemented under [`member2_alignment/`](member2_alignment/README.md). Documentation:
[`docs/member2/`](docs/member2/README.md).

## Member 4 (offline HMM map matching)

Implemented under [`member4_map_matching/`](member4_map_matching/README.md). Documentation:
[`docs/member4/`](docs/member4/README.md). Handoff for Members 5/6:
[`docs/member4/INTEGRATION.md`](docs/member4/INTEGRATION.md).

## Member 5 (native IDR engine)

Implemented under [`member5_engine/`](member5_engine/README.md). C ABI for Member 6:
[`member5_engine/include/idr_engine_api.h`](member5_engine/include/idr_engine_api.h).
Binding notes: [`docs/member5/INTEGRATION.md`](docs/member5/INTEGRATION.md).

## Build

```bash
python3 -m pip install -r member2_alignment/requirements.txt
python3 -m pip install -r member4_map_matching/requirements.txt
python3 member4_map_matching/python/tools/build_synthetic_graph.py
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
PYTHONPATH=member4_map_matching/python python3 -m pytest member4_map_matching/tests/python -q
```

