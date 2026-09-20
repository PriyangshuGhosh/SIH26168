# SIH26168

Repository for the SIH26168 intelligent GNSS-denied navigation system.

## Core Navigation Pipeline

The implemented navigation stack is intentionally focused on non-vision sensing:

`Phone IMU/GNSS → Frame Alignment → AI Speed Estimation → EKF/UKF Fusion → Offline HMM Map Matching → Native C++ Engine → Mobile Navigation UI`

The system is designed to continue estimating vehicle trajectory during GNSS degradation/outage using inertial measurements, learned speed estimation, vehicle constraints, and road-network/map constraints.

Host simulation (labelled **SIMULATION**, not phone sensors):

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target member5_simulation_demo
./build/member5_engine/member5_simulation_demo
```

Android app (no `/sdcard` developer paths): Gradle project `app/` provisions `assets/maps` into `filesDir`. If `speed_estimator.onnx` is absent, the engine uses an explicit **mock** backend.

**ANDROID HARDWARE VALIDATION: NOT AVAILABLE** until a physical device run is recorded.
**ANDROID PERFORMANCE: NOT VALIDATED** until measured on device.
**Real ML: NOT VALIDATED** unless a trained `speed_estimator.onnx` and dataset are present in the checkout.

See [docs/architecture/README.md](docs/architecture/README.md).

## Integration Order

**Member 2 → Member 1 → Member 3 → Member 4 → Member 5 → Member 6**

## Future Extension: V2X / OBU Cooperative Localization

A future hardware phase can extend the current phone-based navigation stack with **V2X communication and an in-vehicle OBU (On-Board Unit)**. The vehicle/OBU can provide cooperative localization measurements such as vehicle position, velocity, heading, and time-synchronized state information, while roadside infrastructure or nearby vehicles can provide additional spatial references.

The intended architecture is:

`Phone IMU + AI Speed + EKF + HMM Map Matching ← V2X/OBU cooperative measurements`

V2X measurements should be treated as another uncertainty-aware EKF measurement source rather than as an unconditional replacement for the existing estimator. Each received message can be validated for freshness, plausibility, coordinate/frame consistency, and reported uncertainty before fusion. This allows the system to fall back gracefully to the existing dead-reckoning pipeline when V2X coverage or communication quality is poor.

The repository currently contains a **software-only V2X simulation** under `sih26168_v2x/`. It is not a physical C-V2X/DSRC radio implementation and must not be presented as hardware-validated V2X.

## Mode-A V2X demo (simulation visualization)

Standalone library: [`sih26168_v2x/`](sih26168_v2x/README.md). Desktop digital twin (not a radio, not Members 1–6):

```bash
PYTHONPATH=sih26168_v2x/python:demo python3 -m sih26168_v2x_demo --demo
```

See [`demo/README.md`](demo/README.md). **V2X RADIO: SIMULATED.**

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

## Member 6 (mobile)

Implemented under [`member6_mobile/`](member6_mobile/README.md). Documentation:
[`docs/member6/`](docs/member6/README.md).

## V2X cooperative localization (MODE A simulation)

Standalone library [`sih26168_v2x/`](sih26168_v2x/README.md). **Software simulation only** — not C-V2X/OBU/Android radio. Optional CMake flag `SIH26168_BUILD_V2X`.

```bash
cmake -S sih26168_v2x -B build-v2x -DCMAKE_BUILD_TYPE=Release
cmake --build build-v2x -j
ctest --test-dir build-v2x --output-on-failure
PYTHONPATH=sih26168_v2x/python python3 -m pytest sih26168_v2x/tests/python -q
```

Do **not** treat this as real V2X until hardware exists and is tested.

```bash
python3 -m pip install -r member2_alignment/requirements.txt
python3 -m pip install -r member4_map_matching/requirements.txt
python3 member4_map_matching/python/tools/build_synthetic_graph.py
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
PYTHONPATH=member4_map_matching/python python3 -m pytest member4_map_matching/tests/python -q
```
