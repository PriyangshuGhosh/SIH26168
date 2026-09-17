# Member 3 — Sensor Fusion

## Contract audit

The repository specification requires the 8-state EKF state `[x, y, vx, vy, yaw, bax, bay, bgz]`. The earlier merged implementation was a 5-state EKF, so this branch uses the required 8-state formulation instead.

Member 3 owns sensor fusion only. Member 2 remains the sole phone-to-vehicle alignment owner; Member 3 consumes `AlignedIMUFrame` and does not duplicate mounting-orientation estimation.

## State and interfaces

State order:

`x = [north_m, east_m, forward_m/s, lateral_m/s, yaw_rad, accel_bias_x, accel_bias_y, gyro_bias_z]ᵀ`

Public interface types are in `member3_fusion/include/member3/fusion_types.h`; the engine is declared in `EKFFusionEngine.hpp`.

`NavigationState` contains timestamp, WGS84 latitude/longitude, reference altitude, vehicle-frame `v_x/v_y`, yaw, 2×2 position covariance, navigation mode, validity, and the latest GNSS/AI acceptance flags.

Member 1 AI speed input is `AiSpeedMeasurement{timestamp, velocity_mps, variance_m2s2, valid}`. A Member 1 predictive standard deviation must be squared before populating `variance_m2s2`.

GNSS input accepts position, quality (`hdop`, satellite count), and optional speed. Set `GnssMeasurement::speed_valid = false` when the receiver does not provide a usable speed; the position update remains usable without a speed value.

## Frames and units

Vehicle convention follows Member 2: +X forward, +Y left, +Z up. Accelerometer values are specific force in m/s² and gyro values are rad/s. Member 2's phone-to-vehicle DCM convention is `a_v = R_vp a_p`, with quaternion order `[w, x, y, z]`.

## EKF prediction

Prediction uses bias-corrected aligned `ax_v`, `ay_v`, and `gz_v`. Vehicle-frame velocity is rotated into local North/East using yaw. Accelerometer and gyro biases are random-walk states and are included in the analytical covariance Jacobian.

Each valid interval is integrated in bounded substeps of `max_prediction_dt_s`; intervals longer than `max_gap_s` are treated as data gaps rather than as one artificial motion step. Data gaps advance the estimator clock and inflate uncertainty.

For Member 2 status other than `FULLY_ALIGNED`, process noise is inflated and the non-holonomic constraint is disabled. `INVALID` samples are ignored.

## Measurement updates and gates

- GNSS position is a 2-D local North/East measurement. The innovation covariance is `S = HPHᵀ + R`; a configurable Mahalanobis/NIS gate defaults to the 95% chi-square threshold 5.991.
- GNSS speed and AI speed measure forward velocity `v_x` and use scalar NIS gating with default threshold 3.841.
- GNSS position uncertainty is estimated as `max(position_sigma_floor, HDOP × gnss_hdop_to_sigma_m)`. The conversion factor is explicitly configurable because HDOP is dimensionless and the current GNSS input contract does not expose receiver covariance.
- NHC is the probabilistic measurement `v_y = 0`, applied only when Member 2 reports `FULLY_ALIGNED`.
- Measurement updates use Joseph covariance form. GNSS position uses LDLT solves rather than explicit matrix inversion.

## Timestamp and invalid-input policy

Duplicate/backward IMU timestamps are ignored. Measurements outside the configured age/lead window are rejected. Delayed measurements may update the filter when still inside that window, but they never rewind the externally visible navigation timestamp; there is intentionally no out-of-sequence replay.

Non-finite and physically invalid IMU, GNSS, and AI inputs are ignored. Covariance is symmetrized after propagation/updates and checked for positive-semidefinite behavior; materially negative eigenvalues are projected back to a minimum variance floor.

## Python references

`member3_fusion/python/reference_ekf.py` provides the process-model, covariance, NHC, and AI-speed reference. `member3_fusion/python/reference_gnss.py` provides the GNSS local-frame conversion, HDOP uncertainty convention, and NIS calculations. Together they provide a lightweight NumPy cross-check of the production mathematics.

## GNSS blackout evaluation

Dead reckoning continues without GNSS. The C++ regression suite includes a deterministic 20 s synthetic straight-line blackout with a fixed 0.03 m/s² accelerometer bias and checks the resulting drift against the known synthetic trajectory. This is a repeatable sensor-bias regression, **not** a real-driving accuracy result.

The repository has no committed ground-truth driving log for Member 3, so quantitative real-driving drift at 10/30/60/120 s remains **NOT VALIDATED**. No `<10%` drift claim is made.

## Build, tests and benchmark

From the repository root:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
./build/member3_fusion/member3_benchmark
```

The Member 3 workflow builds the repository and runs CTest on Ubuntu. It installs the Python test dependencies in an isolated virtual environment so the repository-wide CTest suite is reproducible. The benchmark reports average/p95/p99 desktop latency for IMU prediction, GNSS update, AI-speed update, and a 100 Hz loop. Android/arm64-v8a performance is **NOT VALIDATED** by this module.

## Downstream integration

Downstream code should include `member3/EKFFusionEngine.hpp` for the engine and may include `member3/fusion_types.h` when only the public data contracts are needed. The existing `sih26168::member3::NavigationState` contract is preserved for Member 4/5 consumers.

## Known limitations

1. No delayed-measurement replay or fixed-lag smoothing.
2. Local tangent-plane conversion is intended for vehicle-scale trajectories.
3. HDOP-to-metre conversion is a configurable approximation until receiver covariance is exposed.
4. Altitude is held at the reference GNSS fix because vertical position is not part of the required 8-state model.
5. Real-driving blackout drift and target-device performance require dedicated ground-truth/hardware validation.
