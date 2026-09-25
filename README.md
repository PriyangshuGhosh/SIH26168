# SIH26168 — Intelligent GNSS-Denied Vehicle Navigation

> **Smart India Hackathon 2026 · Problem Statement SIH26168 · ISRO**  
> AI/ML-based intelligent dead reckoning for continuous vehicle navigation when GNSS becomes unavailable.

## 1. What this project does

When a vehicle enters a tunnel, covered parking area, urban canyon, or another GNSS-degraded environment, a phone can lose reliable positioning even though its inertial sensors continue working.

**SIH26168** turns the smartphone into a software-defined dead-reckoning system:

```text
Phone Accelerometer + Gyroscope
              │
              ▼
      M2 · Frame Alignment
              │
              ▼
      M1 · AI Speed Estimator
              │
              ▼
       M3 · EKF Sensor Fusion ◄──── GNSS when available
              │
              ▼
      M4 · Offline HMM Map Matching
              │
              ▼
       M5 · Native Edge Engine
              │
              ▼
        Mobile Navigation UI
```

The important design choice is that **GNSS is a correction source, not a hard dependency**. When GNSS becomes unavailable, the estimator continues from IMU + learned vehicle speed + motion constraints + offline road geometry.

### Current sensing scope

- **Accelerometer + gyroscope:** core inertial inputs.
- **GNSS:** used whenever available to initialize/correct the estimator.
- **Offline road network:** used for map matching and the optional soft road-corridor constraint.
- **Camera / computer vision:** **not part of the current solution**.
- **Magnetometer / compass:** **not required by the current production pipeline**.
- **V2X / OBU:** **future extension; repository implementation is software simulation only**.

---

## 2. Judge-first: see the system in a few minutes

### Recommended demonstration path — current root application

The repository's current judge-facing application is the **React + Vite + Express** application under `src/`.

It provides:

- live/synthetic navigation HUD;
- GNSS blackout simulation;
- ML speed telemetry;
- 8-state EKF telemetry;
- HMM road-match status;
- optional **Road Constraint** toggle;
- sensor diagnostics;
- SpeedGuard safety test;
- deterministic synthetic-drive fallback.

### Start it

Requirements: Node.js 20+ and npm.

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The server loads the committed `final.production.onnx` model through ONNX Runtime Node when the model is available.

### Suggested judge flow

1. Start in **GNSS** mode.
2. Observe the vehicle position, speed, heading, ML telemetry and map-match state.
3. Select **CUT GNSS (TEST OUTAGE)**.
4. Observe the transition to **DEAD_RECKONING**.
5. Enable **ROAD CONSTRAINT: ON** to see the optional soft road-corridor correction.
6. Select **RESTORE GNSS (EXIT OUTAGE)** and observe recovery.
7. Open **DIAGNOSTICS & ONNX RUNTIME** to inspect the processing pipeline.
8. Use **Test SpeedGuard (700 km/h)** to demonstrate invalid-speed rejection.

> **Important:** the default root application includes a deterministic synthetic drive so the architecture can be demonstrated without physical sensors. A synthetic demonstration must not be interpreted as hardware validation.

---

## 3. Architecture at a glance

### Runtime data path

```text
┌───────────────────────┐
│ Smartphone IMU        │
│ ax ay az + gx gy gz   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ M2 · Frame Alignment  │
│ Phone → Vehicle frame │
│ +X forward, +Y left   │
│ +Z up                 │
└───────────┬───────────┘
            │
            ├──────────────────────────────┐
            ▼                              ▼
┌───────────────────────┐        ┌────────────────────┐
│ M1 · AI Speed         │        │ M3 · EKF Fusion     │
│ 6-axis temporal CNN   │───────►│ 8-state estimator   │
│ v + variance + conf.  │        │ GNSS + IMU + NHC    │
└───────────────────────┘        └─────────┬──────────┘
                                           │
                                           ▼
                                ┌────────────────────┐
                                │ M4 · HMM Map Match │
                                │ Offline .roadpack  │
                                └─────────┬──────────┘
                                          │
                                          ▼
                                ┌────────────────────┐
                                │ M5 · Native Engine │
                                │ Stable C ABI       │
                                └─────────┬──────────┘
                                          │
                                          ▼
                                ┌────────────────────┐
                                │ M6 · Mobile UI     │
                                │ Android / JNI path │
                                └────────────────────┘
```

### GNSS outage logic

```text
Healthy GNSS
    │
    ├── GNSS measurements accepted ──► EKF correction
    │
    ▼
GNSS quality degrades / becomes stale
    │
    ▼
DEAD_RECKONING
    │
    ├── IMU propagation
    ├── AI speed measurement
    ├── non-holonomic vehicle constraint
    ├── offline HMM road matching
    └── optional soft road-corridor EKF update
    │
    ▼
GNSS returns
    │
    └── gated GNSS correction → normal navigation
```

---

## 4. The six engineering modules

| Module | Purpose | Main implementation | Status |
|---|---|---|---|
| **M1 — ML** | Estimate forward vehicle speed from 6-axis IMU | Python + PyTorch + ONNX | Implemented |
| **M2 — Alignment** | Convert arbitrary phone mounting into vehicle-frame IMU | C++20/Eigen + Python reference | Implemented |
| **M3 — Fusion** | Estimate position/velocity/heading and control drift | C++20/Eigen + Python reference | Implemented |
| **M4 — Map Matching** | Match trajectory to offline roads | HMM/Viterbi + spatial index | Implemented |
| **M5 — Edge Engine** | Integrate M1–M4 behind a stable API | C++20 + C ABI | Implemented |
| **M6 — Mobile** | Sensor/UI integration and navigation presentation | Android/Kotlin/JNI + current web UI | Implemented with validation gaps |

Detailed module documentation is available in the `docs/` directory and the corresponding module folders.

---

## 5. AI speed-estimation model

The repository contains a committed production ONNX artifact:

```text
final.production.onnx
```

Current root-server contract:

| Property | Value |
|---|---|
| Input | `[B, 200, 6]` Float32 |
| Window | 2 seconds at 100 Hz |
| Channels | `[ax, ay, az, gx, gy, gz]` |
| Architecture | 1D causal CNN / VelocityNet |
| Parameters | 27,266 |
| Outputs | velocity, variance, confidence |
| Runtime | ONNX Runtime |
| Role | AI speed measurement for the fusion layer |

The model is not treated as ground truth. Its predicted speed is passed into the fusion system with uncertainty.

### Important ML validation note

The training repository also contains multiple historical checkpoints, ablations, and research experiments. **Do not mix their metrics with the current deployed pipeline.** The authoritative model/runtime contract is documented in:

- `member1-ml/docs/member1_output_contract.md`
- `member1-ml/docs/production_100hz.md`
- `member1-ml/docs/experiments.md`

The repository intentionally preserves limitations and older experiments so that the evaluation history remains auditable.

---

## 6. Sensor fusion and vehicle constraints

Member 3 uses an 8-state navigation estimate:

```text
[x, y, vx, vy, yaw, bax, bay, bgz]
```

The estimator combines:

- aligned IMU propagation;
- GNSS position/speed updates when valid;
- AI forward-speed measurements with uncertainty;
- non-holonomic vehicle constraints;
- innovation/NIS-style measurement gating.

The goal is to prevent a noisy sensor or an unreliable ML prediction from being accepted as unquestioned truth.

---

## 7. Offline map matching

The map-matching layer is deliberately offline at runtime.

```text
Dead-reckoned position
        │
        ▼
Spatial candidate search
        │
        ▼
Emission score
(distance / uncertainty)
        │
        ▼
Transition score
(network distance / heading / motion)
        │
        ▼
HMM + Viterbi
        │
        ▼
Most likely road segment
```

Runtime road data uses the repository's `.roadpack` format. OSM/GraphML processing is a **map-provisioning step**, not a runtime network dependency.

### Optional road-corridor constraint

The latest integration adds an opt-in **soft** road constraint.

It:

- runs only during GNSS-denied navigation;
- requires a sufficiently confident road match;
- checks road offset and heading consistency;
- applies a bounded EKF position correction;
- does **not** hard-snap the vehicle to a road.

This preserves the underlying estimator while using road geometry as an additional uncertainty-aware measurement.

---

## 8. Edge engine

Member 5 exposes a stable C ABI:

```c
int idr_engine_init(const char* map_db_path, const char* onnx_model_path);
void idr_engine_shutdown(void);

void idr_feed_imu(
    double t,
    double ax, double ay, double az,
    double gx, double gy, double gz
);

void idr_feed_gnss(
    double t,
    double lat, double lon, double alt,
    double speed, double hdop, int num_sats
);

IDRNavigationOutput idr_get_current_state(void);
```

This keeps the mobile layer independent of the internal M1–M4 implementations.

### Production vs test mode

- **Production ONNX:** requires a valid ONNX model and ONNX Runtime-enabled build.
- **Mock speed backend:** explicitly supported for desktop tests/development.
- A missing production model is **not silently treated as a production ML result** by the native engine.

---

## 9. Validation and what the repository can currently claim

### Implemented and reproducible

- Python reference implementations for the major numerical modules.
- C++20 production implementations for alignment, fusion, map matching and the edge engine.
- Unit/integration tests and desktop benchmarks.
- ONNX export and runtime verification.
- Synthetic GNSS-outage simulation.
- Offline road-network/map-matching tests.
- Android build path.
- Software-only V2X simulation.

### Not yet a hardware performance claim

The repository currently does **not** claim:

- measured Android/arm64 real-time performance;
- controlled real-vehicle GNSS-denied accuracy;
- validated end-to-end accuracy on a physical phone in a tunnel;
- physical V2X/OBU radio operation.

Recorded-phone accuracy and target-device performance are explicitly marked as pending in the module documentation.

### Current host-test note

The host CTest suite contains a synthetic end-to-end test that currently exercises the **mock speed backend**. That synthetic test has an outstanding failure in the mock-speed persistence path; it should be fixed before presenting the host test suite as fully green.

This is intentionally called out rather than hidden because the mock path is separate from the bundled ONNX model.

---

## 10. V2X / OBU extension

The repository contains `sih26168_v2x/` as a **future cooperative-localization extension**.

Current status:

| Capability | Status |
|---|---|
| V2X message model | Implemented |
| Cooperative measurement/gating | Implemented in host simulation |
| Replay/simulator | Implemented |
| Physical C-V2X / NR-V2X radio | Not implemented |
| OBU driver | Not implemented |
| Android radio integration | Designed / not implemented |
| Hardware validation | Not validated |

**Do not present the V2X module as a physical radio demonstration.**

---

## 11. Repository map

```text
SIH26168/
├── src/                     # Current root React/TS judge-facing application
├── final.production.onnx    # Bundled ML model used by the root server
│
├── member1-ml/              # Training, evaluation and ONNX export
├── member2_alignment/       # Phone → vehicle frame alignment
├── member3_fusion/          # EKF/UKF sensor fusion
├── member4_map_matching/    # Offline HMM map matching
├── member5_engine/          # Native C++ edge engine + C ABI
├── member6_mobile/          # Native Android/JNI integration path
│
├── android_app/              # WebView packaging of the current root application
├── vizag_nav_app/            # Older native Android prototype
├── idr_app/                  # Additional prototype/integration material
│
├── sih26168_v2x/             # Future V2X cooperative-localization simulation
├── demo/                     # V2X simulation visualization
├── docs/                     # Architecture, interfaces and validation documentation
│
├── CMakeLists.txt            # Host/native build
├── package.json              # Root web application
└── PROJECT_IMPLEMENTATION_HANDBOOK.md
```

### Which application should a judge use?

**Start with the root application (`src/`) using `npm run dev`.**

The repository contains additional Android/native prototypes because the project was developed in parallel across multiple integration paths. They are documented separately and should not be assumed to represent the exact same runtime.

---

## 12. Native Android path

For the current root web application packaged as Android:

```bash
npm install
npm run lint
npm run build:web
gradle -p android_app assembleDebug
```

The resulting APK is:

```text
android_app/app/build/outputs/apk/debug/app-debug.apk
```

**Important:** the standalone WebView APK does not provide the same Node/ONNX Runtime server path as the desktop/root application. Its current dead-reckoning path has an explicit fallback and is therefore **not** a claim of hardware-validated on-device ML inference.

For the lower-level native/JNI integration, see `member6_mobile/` and `member5_engine/`.

---

## 13. Development and test commands

### Root application

```bash
npm install
npm run lint
npm run build:web
npm run dev
```

### Native host build

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
```

### Member 2

```python
python3 -m pip install -r member2_alignment/requirements.txt
PYTHONPATH=member2_alignment/python python3 -m pytest -q
```

### Member 4

```python
python3 -m pip install -r member4_map_matching/requirements.txt
PYTHONPATH=member4_map_matching/python python3 -m pytest member4_map_matching/tests/python -q
```

### V2X simulation

```bash
cmake -S sih26168_v2x -B build-v2x -DCMAKE_BUILD_TYPE=Release
cmake --build build-v2x -j
ctest --test-dir build-v2x --output-on-failure
PYTHONPATH=sih26168_v2x/python python3 -m pytest sih26168_v2x/tests/python -q
```

---

## 14. Documentation for deeper review

| If you want to understand... | Start here |
|---|---|
| Overall architecture | `docs/architecture/README.md` |
| Module ownership/integration | `docs/WORK_DISTRIBUTION.md` |
| ML model contract | `member1-ml/docs/member1_output_contract.md` |
| ML experiments | `member1-ml/docs/experiments.md` |
| 100 Hz production interface | `member1-ml/docs/production_100hz.md` |
| Phone frame alignment | `docs/member2/` |
| EKF/fusion | `docs/member3/` |
| HMM map matching | `docs/member4/` |
| Native engine/C ABI | `docs/member5/` |
| Android integration | `docs/member6/` |
| V2X simulation | `sih26168_v2x/` |

---

## 15. Design principles

1. **No hidden sensor dependency.** The core inertial pipeline uses accelerometer + gyroscope.
2. **No hard map snapping.** Road geometry is an uncertainty-aware constraint.
3. **No silent mock substitution in production native initialization.**
4. **AI predictions carry uncertainty.** They are measurements, not ground truth.
5. **GNSS remains a correction source.** The estimator is designed to continue through outages.
6. **Offline operation matters.** Runtime map matching does not depend on downloading OSM data.
7. **Every performance claim must identify its measurement context.**
8. **Simulation is labelled as simulation.** It is not presented as hardware validation.
9. **Future V2X work is separated from the current validated sensing path.**
10. **Reproducibility over presentation.** Algorithms have reference implementations, tests and documented contracts.

---

## 16. Problem statement alignment

The project directly targets the SIH26168 requirement for a lightweight, edge-deployable intelligent dead-reckoning system that can use smartphone inertial sensing, learned vehicle kinematics, GNSS/INS fusion, map matching, and a mobile navigation interface during GNSS outages.

The implementation is intentionally narrower than the broad problem statement where necessary: the current solution focuses on the **6-axis accelerometer + gyroscope pipeline**, while camera-based sensing, physical V2X/OBU integration, and target-device accuracy/performance remain outside the currently validated implementation.

---

## License

MIT — see [LICENSE](LICENSE).
