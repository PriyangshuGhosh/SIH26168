# SIH26168 — Production-Grade Work Distribution & Deliverables

## 1. Purpose

This document is the team execution contract for SIH26168. It defines ownership, interfaces, deliverables, dependencies, validation expectations, and integration order for the six-member intelligent GNSS-denied navigation system.

The project must be developed as six independently testable modules with explicit contracts. A member is not considered complete when they only have research notes or a notebook; the component must be reproducible, documented, testable, and consumable by its downstream member.

## 2. System Workflow

```text
Phone IMU/GNSS
      |
      v
Member 2: Frame Alignment
      |
      +------> Member 1: AI Speed Estimator
      |                 |
      v                 v
Member 3: EKF/UKF Sensor Fusion <----- GNSS
      |
      v
Member 4: Offline HMM Map Matching
      |
      v
Member 5: Native C++ Edge Engine
      |
      v
Member 6: Mobile Application + Offline Map UI
```

## 3. Team Distribution

| Member | Role | Primary Deliverable | Depends On | Downstream |
|---|---|---|---|---|
| 1 | ML Engineer — Kinematics & Speed Prediction | `speed_estimator.onnx` + inference wrapper | Member 2 / IO-VNBD | Members 3, 5 |
| 2 | Sensor Algorithms Engineer — Calibration & Frame Alignment | `FrameAligner.hpp` + aligned IMU contract | Raw sensors / IO-VNBD | Members 1, 3, 5 |
| 3 | Sensor Fusion Engineer — EKF/UKF | `EKFFusionEngine.cpp` + `NavigationState` | Members 1, 2 + GNSS | Members 4, 5 |
| 4 | Geospatial AI Engineer — Map Matching | `MapMatchingEngine.cpp` + offline map/index | Member 3 + OSM | Members 5, 6 |
| 5 | Edge Systems Engineer — Core Engine | `libidr_engine.so` + `idr_engine_api.h` | Members 1–4 | Member 6 |
| 6 | Mobile Application & UI Engineer | Production APK + offline navigation UI | Member 5 | Final demo |

## 4. Definition of Done

Every member must deliver:

- [ ] Source code committed to the repository.
- [ ] Reproducible build/run instructions.
- [ ] Clearly documented input/output interface.
- [ ] Unit, numerical, or integration validation where applicable.
- [ ] Test data or a repeatable test command.
- [ ] Integration instructions for downstream members.
- [ ] No undocumented machine-specific paths or configuration.
- [ ] A short benchmark/report for the critical performance metric of the module.

---

# Member 1 — ML Engineer: Kinematics & Speed Prediction

## Objective

Build, train, validate, and export a lightweight deep-learning model that predicts forward vehicle velocity from a 6-axis vehicle-aligned IMU stream while reducing sensitivity to road noise, engine vibration, potholes, and shock events.

## Stack

Python 3.10+, PyTorch, Polars/NumPy/Pandas, SciPy, ONNX, ONNX Runtime. Dataset: IO-VNBD.

## Input Contract

- 100 Hz vehicle-aligned IMU.
- Channel order: `[ax, ay, az, gx, gy, gz]`.
- Model input: `[batch, 6, 200]`, Float32.
- 200 samples represent a 2-second temporal window.
- Recommended prediction stride: 10 samples.

## Output Contract

- `estimated_velocity`: `[batch, 1]`, Float32, m/s.
- `velocity_variance`: `[batch, 1]`, Float32, m²/s².
- Serialized model: `speed_estimator.onnx`.
- Target: compact model suitable for native edge/mobile inference.

## Roadmap

1. Parse and clean IO-VNBD data.
2. Align and segment IMU into deterministic windows.
3. Establish a simple baseline before the final 1D-CNN/TCN architecture.
4. Train using Huber and compare against MSE.
5. Evaluate MAE/RMSE and robustness to potholes, braking, acceleration, and vibration.
6. Export to ONNX and validate numerical equivalence.
7. Benchmark model size, latency, memory, and accuracy.

## Deliverables

- `speed_estimator.onnx`
- Training script.
- Preprocessing script/configuration.
- Python inference wrapper.
- ONNX Runtime compatibility test.
- Evaluation report with MAE/RMSE.
- Model I/O specification.
- Latency and memory benchmark.

## Parallel Stub

Downstream members may use a mock speed estimator while the real model is being trained. The stub must expose the same `predict(window) -> (velocity, variance)` interface.

---

# Member 2 — Sensor Algorithms Engineer: Calibration & Frame Alignment

## Objective

Develop the real-time coordinate-frame alignment engine that determines the phone's orientation relative to the vehicle chassis and converts raw phone IMU vectors into the vehicle reference frame.

## Stack

C++20, Eigen3, Python, NumPy, SciPy.

## Input Contract

```text
[timestamp, ax_p, ay_p, az_p, gx_p, gy_p, gz_p]
```

Raw sensor rate: 100 Hz.

## Output Contract

`AlignedIMUFrame`:

```cpp
struct AlignedIMUFrame {
    double timestamp;
    double ax_v, ay_v, az_v;
    double gx_v, gy_v, gz_v;
    double q_pv[4];
    CalibrationStatus status;
};
```

Vehicle convention:

- +X = forward.
- +Y = left.
- +Z = up.
- Quaternion order = `[w, x, y, z]`.

## Roadmap

1. Detect quasi-static intervals and estimate gravity direction.
2. Estimate initial roll and pitch.
3. Estimate dynamic yaw only from reliable vehicle-motion evidence; do not blindly interpret turns or potholes as forward direction.
4. Build DCM/quaternion rotation from phone frame to vehicle frame.
5. Validate with synthetic and recorded sequences.
6. Port the validated reference implementation to allocation-light C++20/Eigen.

## Deliverables

- Python reference implementation.
- `FrameAligner.hpp` / C++ implementation.
- `calibration_types.h`.
- Rotation convention document.
- Test vectors and expected outputs.
- Calibration confidence/status handling.
- Performance benchmark.

## Critical Failure Cases

Phone movement, turns, braking, potholes, weak acceleration, poor static periods, and incorrect mounting assumptions must be detected or reflected through confidence/status rather than silently producing false certainty.

---

# Member 3 — Sensor Fusion Engineer: EKF/UKF & Kinematic Constraints

## Objective

Fuse aligned IMU, GNSS, AI-predicted forward speed, and valid vehicle-motion constraints into a continuous navigation state that remains usable during GNSS outages.

## Stack

C++20, Eigen3, Python, FilterPy/SciPy.

## Input Contract

- Member 2: aligned IMU at 100 Hz.
- Member 1: forward speed + variance at approximately 20 Hz.
- GNSS: position/speed/quality measurements when available.

## State Contract

```text
[x, y, vx, vy, yaw, bax, bay, bgz]
```

Output `NavigationState` must include timestamp, WGS84 position, vehicle-frame velocity, heading, position covariance, and navigation mode.

## Roadmap

1. Implement the 8-state process model.
2. Propagate using aligned IMU acceleration and yaw rate.
3. Add GNSS position/speed measurement updates.
4. Add AI speed as a probabilistic measurement using Member 1's supplied variance.
5. Apply the non-holonomic constraint `vy ≈ 0` only when the vehicle-motion assumption is valid.
6. Add innovation/residual gating.
7. Simulate GNSS blackouts and quantify drift.
8. Port validated Python mathematics to production C++/Eigen.

## Deliverables

- Python EKF/UKF reference.
- `fusion_types.h`.
- `EKFFusionEngine.cpp/.hpp`.
- State, process, and measurement equations.
- Covariance tuning configuration.
- GNSS outage simulation.
- Position/velocity/heading error benchmark.
- Runtime benchmark.

---

# Member 4 — Geospatial AI Engineer: Offline HMM Map Matching

## Objective

Build an offline map-matching engine that takes noisy EKF/dead-reckoned coordinates and identifies the most likely road geometry using an HMM and spatial indexing.

## Stack

Python: OSMnx, NetworkX, Rtree, Shapely. C++ runtime with an offline spatial index and road graph.

## Input Contract

`NavigationState` from Member 3:

- latitude/longitude or local x/y.
- heading.
- position covariance.
- timestamp.

## Output Contract

```cpp
struct MapMatchedPosition {
    double timestamp;
    double lat_snapped, lon_snapped;
    double heading_snapped_rad;
    int64_t road_segment_id;
    double confidence_score;
    bool is_on_road_network;
};
```

## Roadmap

1. Extract OSM road data for the target area.
2. Build offline road graph and R-tree/spatial index.
3. Generate candidate road segments within a configurable search radius.
4. Score emissions using perpendicular distance and uncertainty.
5. Score transitions using network distance, displacement, and heading consistency.
6. Run Viterbi decoding over a sliding state window.
7. Package map/index data for deterministic offline queries.

## Deliverables

- OSM preprocessing tool.
- Offline map/index format.
- Python HMM reference.
- C++/runtime map matcher.
- Road segment confidence metric.
- Offline test dataset.
- Accuracy and runtime benchmark.

## Critical Cases

Intersections, parallel roads, sparse observations, GPS jumps, incorrect heading, roads with multiple lanes, and temporary off-network positions must not cause unstable snapping.

---

# Member 5 — Edge Systems Engineer: Core C++ Engine & GNSS Outage Handler

## Objective

Integrate Members 1–4 into a high-performance native C++ engine and expose a stable ABI for the mobile application.

## Stack

C++20, Eigen3, ONNX Runtime C++, CMake, Android NDK, C ABI/JNI.

## Input Contract

- `speed_estimator.onnx` from Member 1.
- `FrameAligner` from Member 2.
- `EKFFusionEngine` from Member 3.
- `MapMatchingEngine` from Member 4.

## Output Contract

- `libidr_engine.so` for Android/Linux.
- `idr_engine_api.h` stable C ABI.
- Initialization/shutdown.
- IMU feed.
- GNSS feed.
- Current navigation state retrieval.

Example API:

```c
int idr_engine_init(const char* map_db_path, const char* onnx_model_path);
void idr_engine_shutdown();
void idr_feed_imu(double timestamp, double ax, double ay, double az,
                  double gx, double gy, double gz);
void idr_feed_gnss(double timestamp, double lat, double lon, double alt,
                   double speed, double hdop, int num_sats);
IDRNavigationOutput idr_get_current_state();
```

## Roadmap

1. Establish CMake architecture and module boundaries.
2. Separate 100 Hz sensor ingestion from slower inference/fusion stages.
3. Load ONNX once and reuse buffers where practical.
4. Implement GNSS-quality state machine.
5. Detect poor GNSS using availability, update age, HDOP, satellite count, and other validated quality signals.
6. Transition to dead reckoning without resetting useful state.
7. Provide thread-safe C ABI.
8. Build and test Android `arm64-v8a` artifact.

## Deliverables

- CMake project.
- Integrated native engine.
- ONNX Runtime wrapper.
- GNSS deficit/outage state machine.
- `idr_engine_api.h`.
- `libidr_engine.so`.
- Android build instructions.
- End-to-end CPU, memory, latency, and transition-time report.

## Performance Requirement

The system should have an explicit measured latency target for GNSS mode transitions and should report measured results. Do not claim a sub-10 ms guarantee unless it is actually benchmarked on the target hardware.

---

# Member 6 — Mobile Application & UI Engineer

## Objective

Build the user-facing navigation application that captures phone sensors, feeds the native engine, renders the offline map, and clearly demonstrates seamless navigation through a GNSS blackout.

## Stack

Flutter/Dart FFI or native Android Kotlin/JNI, MapLibre/Mapbox-compatible offline mapping, Android sensor/GNSS APIs, MBTiles/vector tiles.

## Input Contract

- Member 5 `idr_engine_api.h`.
- Member 5 `libidr_engine.so`.
- Offline map package/configuration.

## Roadmap

1. Build app shell and permissions.
2. Capture accelerometer, gyroscope, and GNSS data.
3. Stream sensor data to the native library safely.
4. Integrate C ABI through Dart FFI or Kotlin JNI.
5. Render an offline map with internet disabled.
6. Poll navigation state at approximately 10 Hz.
7. Smooth vehicle-marker motion with interpolation.
8. Add a `Simulate GNSS Outage` control.
9. Show GNSS/DR mode, speed, heading, and confidence/debug information.

## Deliverables

- Mobile application source.
- FFI/JNI bridge.
- Offline map package/configuration.
- Navigation screen.
- GNSS blackout simulation.
- APK build instructions.
- Hardware test procedure.
- Final judging/demo script.

---

# 5. Interface Contracts

| Interface | Producer | Consumer | Contract |
|---|---|---|---|
| Raw IMU | Device / dataset | Member 2 | 100 Hz, timestamped 6-axis sensor data |
| Aligned IMU | Member 2 | Members 1, 3, 5 | Vehicle frame, +X forward, +Y left, +Z up |
| AI speed | Member 1 | Members 3, 5 | `v_x` + variance, approximately 20 Hz |
| Navigation state | Member 3 | Members 4, 5 | Position, velocity, yaw, covariance, mode |
| Map match | Member 4 | Members 5, 6 | Snapped coordinate, segment ID, confidence |
| Native engine API | Member 5 | Member 6 | Stable C ABI |
| Mobile output | Member 6 | Judges/end user | Smooth offline navigation experience |

## Mocking Rule

A downstream member may use a mock implementation only when the mock follows the same interface and units as the real component. Once the real component is available, integration tests must run against the real implementation.

---

# 6. Integration Order

```text
2 → 1 → 3 → 4 → 5 → 6
```

### Gate A — Sensor Alignment

Member 2 demonstrates that raw phone IMU data can be converted into a stable vehicle-frame stream.

### Gate B — AI Speed

Member 1 consumes Member 2 output and produces validated speed estimates plus ONNX export.

### Gate C — Sensor Fusion

Member 3 reproduces a trajectory using IMU + GNSS + AI speed and demonstrates controlled GNSS outage behavior.

### Gate D — Map Matching

Member 4 map-matches the Member 3 trajectory completely offline.

### Gate E — Native Integration

Member 5 executes the full pipeline without Python dependencies in the runtime path.

### Gate F — Mobile Demo

Member 6 runs the native engine from the phone, displays the offline map, and demonstrates a repeatable GNSS blackout.

---

# 7. Layman's Project Explanation

The problem is simple: when a smartphone enters a tunnel, covered parking area, or dense urban environment, GNSS can become unreliable. Raw accelerometer and gyroscope data can continue operating, but integrating them directly causes drift because of gravity, phone mounting angle, vibration, potholes, braking, and sensor bias.

The system solves this as a chain:

1. **Member 2 aligns the phone:** figures out how the phone is mounted and converts sensor measurements into the vehicle coordinate system.
2. **Member 1 estimates speed with AI:** learns vehicle motion patterns and provides forward speed with uncertainty instead of trusting raw acceleration alone.
3. **Member 3 maintains the navigation state:** fuses GNSS, IMU, AI speed, and vehicle constraints. GNSS corrects drift when healthy; the estimator continues when GNSS disappears.
4. **Member 4 uses the road network:** compares the drifting trajectory against a locally stored road graph and chooses the most plausible road segment.
5. **Member 5 turns the algorithms into an edge engine:** integrates everything into a native C++ runtime suitable for a phone.
6. **Member 6 presents the result:** shows a smooth vehicle marker on an offline map and demonstrates that navigation continues during GNSS loss.

---

# 8. Engineering Rules

1. Define units and coordinate conventions before implementing algorithms.
2. Never silently change an interface consumed by another member.
3. Any interface change must be documented and communicated to downstream members.
4. Keep reference/prototype code separate from production C++ code.
5. Avoid hard-coded absolute paths.
6. Every performance claim must have a benchmark command and hardware/software context.
7. AI predictions are measurements with uncertainty, not ground truth.
8. Do not claim GNSS-denied accuracy without a controlled outage experiment.
9. Prefer deterministic tests over visual/manual-only validation.
10. Keep the mobile application independent of the internal mathematics of Members 1–4; it should talk to the native engine API only.

## Recommended Repository Structure

```text
SIH26168/
├── docs/
│   └── WORK_DISTRIBUTION.md
├── member1_ml/
├── member2_alignment/
├── member3_fusion/
├── member4_map_matching/
├── member5_engine/
├── member6_mobile/
├── tests/
├── data/                 # metadata/config only; do not commit restricted datasets
└── README.md
```

## Final Deliverable

The final system is considered complete only when the six modules operate together in a repeatable hardware demonstration: healthy GNSS → controlled GNSS degradation/outage → continued dead reckoning → offline map correction → smooth mobile visualization.
