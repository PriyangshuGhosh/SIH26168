# SIH26168 — Project Implementation Handbook & AI Prompts

> Team execution document for the six-module intelligent navigation / GNSS-denied dead-reckoning system.

## 1. Project Objective

Build a smartphone-based navigation system that continues estimating vehicle position when GNSS/GPS becomes unavailable in tunnels, covered parking areas, urban canyons, and other signal-denied environments.

The system combines:

**Phone IMU → automatic frame alignment → AI speed estimation → EKF/UKF sensor fusion + vehicle constraints → offline map matching → native edge engine → mobile navigation UI**

The key engineering principle is modular ownership with explicit interface contracts. Each member must deliver a testable component, not just research notes or isolated notebooks.

---

## 2. Team Work Distribution

| Member | Role | Primary Deliverable | Main Integration Dependency |
|---|---|---|---|
| 1 | ML Engineer | `speed_estimator.onnx` + inference wrapper | Member 2 IMU → Members 3/5 |
| 2 | Sensor Algorithms Engineer | Calibration/frame-alignment module | Raw IMU → Members 1/3 |
| 3 | Sensor Fusion Engineer | EKF/UKF C++/Python implementation | Members 1/2 + GNSS → Members 4/5 |
| 4 | Geospatial AI Engineer | Offline HMM map matcher | Member 3 trajectory → Members 5/6 |
| 5 | Edge Systems Engineer | Integrated C++ engine/shared library | Members 1–4 → Member 6 |
| 6 | Mobile Application & UI Engineer | Android/iOS application | Member 5 API → final demo |

### Definition of Done

A module is considered delivered only when it has:

1. Source code in the repository.
2. A reproducible build/run procedure.
3. Unit or numerical validation where applicable.
4. Clearly documented input/output interfaces.
5. A small demo/test dataset or test command.
6. Integration instructions for the next member.
7. No dependency on undocumented local paths or machine-specific configuration.

---

# 3. Member 1 — ML Engineer: Kinematics & Speed Prediction

## Role & Objective

Build, train, validate, and export a lightweight deep-learning model that suppresses road/vehicle vibration effects and predicts forward vehicle velocity (`v_x`) and acceleration from a dynamic gravity-aligned 6-axis IMU stream.

### Tech Stack

- Python
- PyTorch
- NumPy / Polars / Pandas
- SciPy
- ONNX
- ONNX Runtime
- Dataset: IO-VNBD inertial/odometry benchmark dataset

### Interface Contract

**Input:** 100 Hz aligned IMU tensor:

`[a_x, a_y, a_z, omega_x, omega_y, omega_z]`

**Output:**

- Estimated forward speed `v_x` in m/s
- Estimated acceleration where required
- Model uncertainty / variance
- `speed_estimator.onnx`
- Python/C++ inference wrapper

### Roadmap

**Phase 1 — Data preprocessing**
- Parse IO-VNBD.
- Convert data into 100 Hz windows.
- Recommended baseline: 200 samples = 2 s window, 50% overlap.
- Attach ground-truth velocity labels.
- Create deterministic train/validation/test splits.

**Phase 2 — Architecture & denoising**
- Start with 1D CNN + TCN or ResNet-1D.
- Establish a simple baseline before increasing complexity.
- Evaluate high-pass/band-pass filtering for vibration/noise suppression.

**Phase 3 — Training & validation**
- Compare MSE and Huber loss.
- Track MAE/RMSE against ground-truth velocity.
- Test robustness to pothole spikes, idling vibration, braking, and acceleration.

**Phase 4 — Quantization & handoff**
- Export PyTorch → ONNX.
- Benchmark FP32, FP16, and INT8 where supported.
- Deliver model, inference wrapper, preprocessing configuration, and benchmark results to Member 5.

### Required Deliverables

- `speed_estimator.onnx`
- Training script
- Dataset preprocessing script
- Inference wrapper
- Evaluation report
- Model input/output specification
- Latency and memory benchmark

### AI Prompt

> You are a senior edge-ML engineer. Help implement a lightweight 1D temporal model that predicts vehicle forward velocity from 100 Hz 6-axis IMU data. Use IO-VNBD-style inertial/odometry data. Start with a reproducible preprocessing pipeline using 2-second windows with 50% overlap, avoid data leakage between trajectories, compare a compact 1D CNN/TCN baseline, train with Huber and MSE losses, report MAE/RMSE, and export the best model to ONNX. Prioritize inference latency, model size, numerical stability, and deployment on constrained hardware. Produce production-quality Python code with configuration separated from implementation.

---

# 4. Member 2 — Sensor Algorithms Engineer: Calibration & Frame Alignment

## Role & Objective

Develop the dynamic coordinate-alignment engine that estimates the phone's orientation relative to the vehicle body frame and transforms raw phone IMU data into vehicle-frame measurements.

### Tech Stack

- Python
- NumPy
- SciPy
- C++20
- Eigen3

### Interface Contract

**Input:**

`[a_x^p, a_y^p, a_z^p, omega_x^p, omega_y^p, omega_z^p]`

**Output:**

`[a_x^v, a_y^v, a_z^v, omega_x^v, omega_y^v, omega_z^v]`

### Roadmap

**Phase 1 — Static alignment**
- Low-pass acceleration during quasi-static periods.
- Estimate gravity direction.
- Calculate initial roll and pitch.

**Phase 2 — Dynamic yaw alignment**
- Detect reliable forward-acceleration segments.
- Estimate heading/yaw misalignment.
- Quantify confidence rather than assuming every acceleration event is valid.

**Phase 3 — DCM / quaternion transformation**
- Construct `R_p^v(phi, theta, psi)`.
- Transform acceleration and angular-rate vectors into the vehicle frame.
- Validate against known driving sequences.

**Phase 4 — C++ port**
- Implement numerical core with Eigen3.
- Keep the hot path allocation-free where practical.
- Provide deterministic unit tests.

### Required Deliverables

- Python reference implementation
- C++20/Eigen implementation
- Rotation convention document
- Test vectors and expected outputs
- Alignment confidence/status flag
- Performance benchmark

### AI Prompt

> Act as a sensor-fusion/IMU calibration engineer. Design a robust phone-to-vehicle coordinate-frame alignment algorithm using accelerometer and gyroscope data. Explicitly define coordinate conventions, rotation order, DCM/quaternion equations, gravity extraction, static roll/pitch estimation, and a cautious dynamic yaw estimator. Identify failure cases such as turns, braking, potholes, phone movement, and weak acceleration. Implement a Python reference version with NumPy/SciPy and then provide a numerically equivalent C++20/Eigen implementation with unit tests.

---

# 5. Member 3 — Sensor Fusion Engineer: EKF/UKF & Kinematic Constraints

## Role & Objective

Build the core state estimator combining aligned IMU, GNSS, AI-predicted forward speed, and vehicle-motion constraints into a continuous trajectory.

### Tech Stack

- Python
- FilterPy / SciPy
- C++20
- Eigen3

### Interface Contract

**Input:**

- Aligned IMU from Member 2
- AI speed from Member 1
- GNSS position/speed when available

**Output state:**

`[x, y, v_x, v_y, psi, b_ax, b_ay, b_omega_z]`

Delivered to Members 4 and 5.

### Roadmap

**Phase 1 — State & prediction model**
- Define the 8D state and coordinate frame.
- Implement IMU-driven propagation.
- Validate Jacobians numerically.

**Phase 2 — Measurement updates & NHC**
- Add GNSS position/speed updates.
- Apply non-holonomic constraints such as approximately zero lateral vehicle velocity when valid.
- Gate measurements using innovation/residual checks.

**Phase 3 — AI speed integration**
- Use Member 1's predicted `v_x` as a measurement, not as unquestioned ground truth.
- Incorporate model uncertainty into the measurement covariance.
- Gracefully handle unavailable/low-confidence AI predictions.

**Phase 4 — C++ engine**
- Port the validated algorithm to Eigen3.
- Target 10 Hz mobile operation and high-rate edge operation as required by the final architecture.

### Required Deliverables

- Python EKF/UKF reference
- C++ implementation
- State/process/measurement equations
- Covariance tuning configuration
- GNSS outage simulation tests
- Drift/error benchmark

### AI Prompt

> Act as a senior inertial-navigation engineer. Build an EKF for a ground vehicle using an 8-state vector [x, y, vx, vy, yaw, bax, bay, bgz]. Derive the discrete prediction model from aligned IMU data, define GNSS position/speed updates, incorporate AI speed as a probabilistic measurement with supplied variance, and apply non-holonomic constraints only when their assumptions are valid. Include innovation gating, covariance propagation, numerical stability checks, and GNSS-outage simulation. Provide a Python reference implementation followed by C++20/Eigen production code.

---

# 6. Member 4 — Geospatial AI Engineer: Offline Map Matching

## Role & Objective

Build an offline map-matching engine that projects the estimated dead-reckoned trajectory onto valid road segments using spatial indexing and an HMM.

### Tech Stack

- Python: OSMnx, NetworkX, Rtree, Shapely
- C++: spatial-index library + selected routing/map libraries
- Offline vector road data

### Interface Contract

**Input:** EKF trajectory `(x,y)` or `(lat,lon)`.

**Output:**

- Snapped coordinate `(x_snapped, y_snapped)`
- Active road segment ID
- Match confidence/status

### Roadmap

**Phase 1 — OSM extraction & graphing**
- Extract target-area road data.
- Build local road graph.
- Build R-tree/spatial index.

**Phase 2 — HMM emissions**
- Compute candidate road segments.
- Use distance/error models to score observations.

**Phase 3 — HMM transitions**
- Compare network shortest-path distance with trajectory displacement.
- Penalize physically/network-impossible transitions.

**Phase 4 — Offline packaging**
- Package map data and spatial index for offline use.
- Provide a deterministic local query API.

### Required Deliverables

- OSM preprocessing tool
- Local map/index format
- Python HMM reference
- C++/runtime implementation
- Match confidence metric
- Offline test dataset

### AI Prompt

> Act as a geospatial navigation engineer. Design an offline HMM map matcher for a noisy dead-reckoned vehicle trajectory. Use a spatial index to generate road candidates, Gaussian-like emission scores based on perpendicular distance, and transition scores based on road-network distance versus observed displacement and heading. Handle intersections, parallel roads, GPS jumps, sparse observations, and GNSS outages. Provide a Python reference implementation using Shapely/NetworkX/Rtree and then outline a production C++ offline architecture.

---

# 7. Member 5 — Edge Systems Engineer: Core C++ Engine & GNSS Outage Handler

## Role & Objective

Integrate Members 1–4 into a high-performance C++ engine and expose a stable API for mobile integration.

### Tech Stack

- C++20
- ONNX Runtime C++ API
- CMake
- Eigen3
- Android NDK
- C ABI / JNI

### Interface Contract

**Input:** Member 1 ONNX model + Members 2–4 C++ modules.

**Output:**

`libidr_engine.so` / static library as appropriate, with a stable C-facing API.

Example API:

```c
init_engine();
push_imu_data(...);
push_gnss_data(...);
get_current_location(...);
get_navigation_status(...);
```

### Roadmap

**Phase 1 — Architecture & pipeline**
- Establish CMake project structure.
- Define module interfaces.
- Separate high-rate sensor ingestion from slower inference/fusion stages.
- Recommended initial scheduling target: IMU 100 Hz, AI 20 Hz, EKF according to validated implementation requirements.

**Phase 2 — ONNX Runtime integration**
- Load Member 1 model once.
- Reuse buffers where possible.
- Benchmark inference latency and memory.

**Phase 3 — GNSS deficit handler**
- Detect GNSS degradation/dropout using availability and quality indicators.
- Switch estimation modes without resetting state unnecessarily.
- Measure actual transition latency rather than assuming a target.

**Phase 4 — C bindings & shared library**
- Expose stable ABI.
- Build for the selected Android architecture(s).
- Add integration tests callable from the mobile layer.

### Required Deliverables

- CMake project
- Integrated native library
- ONNX Runtime execution wrapper
- GNSS outage state machine
- C API header
- Android build artifact
- End-to-end latency/CPU/memory report

### AI Prompt

> Act as a senior embedded C++ systems architect. Design a modular C++20 engine that integrates IMU frame alignment, ONNX speed inference, EKF state estimation, and offline map matching. Use CMake, Eigen3, ONNX Runtime, and Android NDK-compatible C bindings. Define thread ownership, queues/ring buffers, timing, synchronization, error handling, model lifetime, memory ownership, and ABI boundaries. Add a GNSS-quality state machine that transitions between GNSS-assisted and dead-reckoning modes safely. Prioritize deterministic latency and observability over premature micro-optimization.

---

# 8. Member 6 — Mobile Application & UI Engineer

## Role & Objective

Build the user-facing navigation application that consumes the native engine and renders a smooth vehicle position on an offline map.

### Tech Stack

- Flutter/Dart **or** native Android Kotlin + JNI
- Mapbox Mobile SDK / Flutter Map as selected by the team
- Offline vector tiles
- Android sensors and GNSS APIs

### Interface Contract

**Input:** Member 5 shared library and C API.

**Output:** Production-style APK/IPA demonstration application showing:

- Current position
- Heading
- GNSS availability/status
- Dead-reckoning state
- Offline map
- Smooth vehicle marker

### Roadmap

**Phase 1 — App shell & sensor streaming**
- Sensor permissions.
- GNSS and IMU acquisition.
- Native bridge connection.

**Phase 2 — Offline map**
- Store vector map data locally.
- Verify operation with internet disabled.

**Phase 3 — FFI/JNI bridge**
- Connect Dart FFI or Kotlin JNI to Member 5's API.
- Handle lifecycle, threading, and native errors correctly.

**Phase 4 — UI & demo simulation**
- Smooth marker interpolation.
- GNSS blackout simulation control.
- Display clear system state and confidence.
- Prepare a repeatable judging demonstration.

### Required Deliverables

- Mobile project
- Native bridge implementation
- Offline map package/configuration
- Navigation screen
- GNSS blackout simulation
- APK build instructions
- Demo script

### AI Prompt

> Act as a senior mobile systems engineer. Build an Android navigation prototype that consumes a C ABI from a native C++ dead-reckoning engine. Design the JNI/FFI boundary, sensor ingestion, lifecycle management, background processing, error handling, and offline vector-map rendering. The UI must remain smooth while native estimation runs asynchronously. Include a GNSS blackout simulation mode and clearly show GNSS/DR status. Prioritize reliability and demonstrability over decorative UI.

---

# 9. End-to-End Workflow in Layman's Terms

## The Problem

When a vehicle enters a tunnel, covered parking area, or dense urban environment, the phone can lose reliable GNSS signals. A normal navigation application may freeze, jump, or become inaccurate.

Phone motion sensors can continue operating, but raw accelerometer and gyroscope measurements contain gravity, phone orientation errors, engine vibration, pothole shocks, braking effects, and other noise. Integrating those errors indefinitely causes position drift.

## How Our System Solves It

1. **Member 2 — Auto-align the phone**
   - Determine how the phone is mounted.
   - Transform its measurements into the vehicle coordinate frame.

2. **Member 1 — Estimate vehicle speed with AI**
   - Learn vehicle motion patterns from IMU data.
   - Reduce the effect of bumps and vibration.
   - Provide forward-speed estimates with uncertainty.

3. **Members 3 & 5 — Maintain the navigation state**
   - Fuse GNSS, IMU, AI speed, and vehicle-motion constraints.
   - When GNSS is healthy, use it to correct accumulated error.
   - When GNSS becomes unavailable, continue with inertial/dead-reckoning estimation.

4. **Member 4 — Correct drift using the road network**
   - Compare the estimated trajectory with a locally stored road map.
   - Select the most plausible road segment.
   - Keep the trajectory physically and geographically plausible.

5. **Member 6 — Show the result**
   - Render the estimated vehicle location on an offline map.
   - Keep the marker moving smoothly during simulated or real GNSS outages.

---

# 10. Integration Order

The team should integrate in this order:

**2 → 1 → 3 → 4 → 5 → 6**

### Integration gates

**Gate A:** Member 2 can convert raw IMU into stable vehicle-frame data.

**Gate B:** Member 1 can estimate speed from Member 2's output and export ONNX.

**Gate C:** Member 3 can reproduce a trajectory in Python with GNSS and AI-speed inputs.

**Gate D:** Member 4 can map-match Member 3's trajectory entirely offline.

**Gate E:** Member 5 can execute the complete pipeline natively without Python dependencies.

**Gate F:** Member 6 can consume Member 5's C API and demonstrate continuous navigation during GNSS loss.

Do not wait until the final week to integrate. Each gate should be tested as soon as the upstream contract stabilizes.

---

# 11. Repository Structure

Recommended structure:

```text
SIH26168/
├── docs/
│   ├── architecture.md
│   ├── interfaces.md
│   └── testing.md
├── member1_ml/
│   ├── data/
│   ├── preprocessing/
│   ├── training/
│   ├── models/
│   └── inference/
├── member2_alignment/
│   ├── python/
│   ├── cpp/
│   └── tests/
├── member3_fusion/
│   ├── python/
│   ├── cpp/
│   └── tests/
├── member4_map_matching/
│   ├── preprocessing/
│   ├── python/
│   ├── cpp/
│   └── maps/
├── member5_engine/
│   ├── include/
│   ├── src/
│   ├── tests/
│   ├── cmake/
│   └── models/
├── member6_mobile/
│   └── app/
├── scripts/
├── tests/
└── PROJECT_IMPLEMENTATION_HANDBOOK.md
```

---

# 12. Team Engineering Rules

- Never commit large raw datasets into Git.
- Use Git LFS or external dataset storage when appropriate.
- Every module must document units, coordinate frames, sample rate, timestamp semantics, and ownership of memory.
- Never silently change an interface; update `docs/interfaces.md` first.
- Every performance claim must include hardware, build mode, input size, and measurement method.
- Keep Python versions as reference implementations; production runtime should not depend on Python unless explicitly agreed.
- Do not hard-code absolute paths, API keys, device IDs, or personal machine settings.
- Prefer small pull requests with one logical change.
- Add tests before changing numerical algorithms.
- Keep experimental notebooks separate from production modules.
- Record assumptions and known failure modes.

---

# 13. Minimum Final Demo

The final judging/demo path should show:

1. Vehicle starts with healthy GNSS.
2. System initializes and shows aligned motion/navigation state.
3. GNSS is intentionally disabled or simulated as unavailable.
4. Native engine switches to dead reckoning.
5. AI speed remains available from IMU.
6. EKF continues estimating the vehicle trajectory.
7. Offline map matcher constrains the path to the road network.
8. Mobile marker continues moving without internet/GNSS.
9. GNSS is restored.
10. System reacquires GNSS and corrects accumulated error without an obvious UI jump.

The team should record quantitative metrics for the demo: position error during outage, speed RMSE, outage transition latency, map-match accuracy, CPU usage, memory usage, and application frame smoothness.

---

# 14. AI Usage Policy

AI tools may be used for implementation assistance, debugging, documentation, test generation, and research exploration. However:

- Team members remain responsible for every line merged into the repository.
- AI-generated numerical algorithms must be validated against known equations and test cases.
- Never accept an AI claim about sensor physics without verification.
- Never paste secrets, credentials, private datasets, or unpublished sensitive material into external AI systems.
- Every AI-assisted module must pass the same tests and review requirements as human-written code.

---

# 15. Success Metrics

The project should be evaluated as a system rather than by isolated model accuracy.

| Area | Metric |
|---|---|
| AI speed estimation | MAE / RMSE / inference latency / model size |
| Frame alignment | orientation error / stability / computation time |
| Sensor fusion | position drift during GNSS outage / velocity error |
| Map matching | candidate/match accuracy / query latency |
| Native engine | end-to-end latency / CPU / RAM |
| Mobile app | FPS / battery impact / crash-free operation |
| Overall system | outage continuity / recovery behavior / reproducibility |

**Final principle:** the winning system is not the one with the fanciest individual algorithm. It is the one whose six components work together reliably, offline, under realistic GNSS-denied conditions.
