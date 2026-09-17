# Member 3 — Sensor Fusion

## Contract audit

The repository specification requires the 8-state EKF state `[x, y, vx, vy, yaw, bax, bay, bgz]`. The previous merged implementation was a 5-state EKF (`[north, east, forward velocity, lateral velocity, yaw]`), so it was **not compliant** with the state contract. This completion pass replaces that formulation with the required 8-state model. The original 5-state implementation and its eight basic tests are recorded in merged PR #5.

## Frames and units

Member 2 is the sole phone→vehicle alignment owner. Member 3 consumes `AlignedIMUFrame` directly and does not estimate mounting orientation. Vehicle axes are +X forward, +Y left, +Z up; accelerometer is specific force in m/s² and gyro is rad/s. Member 2 defines the phone→vehicle DCM as `a_v = R_vp a_p` and quaternion order `[w,x,y,z]`.

## EKF

State:

`x = [north_m, east_m, forward_m/s, lateral_m/s, yaw_rad, accel_bias_x, accel_bias_y, gyro_bias_z]ᵀ`

Prediction uses bias-corrected `ax_v`, `ay_v`, and `gz_v`. Position is propagated by rotating vehicle velocity into local North/East using yaw. Biases follow random walks. Process covariance is propagated with the analytical Jacobian.

For Member 2 status other than `FULLY_ALIGNED`, process noise is inflated and NHC is disabled. `INVALID` samples are ignored.

## Measurements and gates

- GNSS position is a 2-D measurement in the local North/East frame. Its innovation covariance is `S = HPHᵀ + R`; a Mahalanobis/NIS test rejects measurements above the configurable 95% chi-square threshold 5.991.
- GNSS speed and AI speed measure the forward-speed state `vx`. Both use scalar NIS gating at default threshold 3.841.
- Member 1's predictive standard deviation must be squared to populate `AiSpeedMeasurement::variance_m2s2`; no arbitrary fixed confidence replaces the supplied uncertainty.
- NHC is the probabilistic measurement `vy = 0`, only when Member 2 reports `FULLY_ALIGNED`.
- Measurement updates use Joseph covariance form. GNSS position uses Eigen LDLT solves instead of explicit `S.inverse()`.

## Timestamp and invalid input behavior

Duplicate/backward IMU timestamps are ignored. Measurements outside the configured age/lead window are rejected because this implementation does not replay out-of-sequence measurements. A gap over 1 s advances time without integrating a large artificial motion step and inflates uncertainty. Non-finite and physically invalid GNSS/AI data are ignored.

## Blackout evaluation

Dead reckoning remains active without GNSS. The repository currently contains deterministic synthetic tests for covariance growth and filter continuity, but **quantitative real-driving drift is NOT VALIDATED** because no ground-truth driving log is committed for this module. Therefore no `<10%` drift claim is made. The required evaluation should report position, velocity and yaw error at 10/30/60/120 s when ground truth is supplied.

## API

```cpp
#include "member3/EKFFusionEngine.hpp"
sih26168::member3::EKFFusionEngine fusion;
fusion.predict(aligned, sih26168::member3::NavigationMode::DEAD_RECKONING);
fusion.updateGnss(gnss);
fusion.updateAiSpeed(ai);
const auto& nav = fusion.state();
```

`NavigationState`: timestamp seconds; WGS84 latitude/longitude degrees; altitude metres; vehicle-frame `v_x/v_y` m/s; yaw rad; 2×2 position covariance m²; mode; validity; acceptance flags. For validation/downstream adapters, `stateVector()` exposes all 8 states and `covariance()` exposes the complete 8×8 covariance.

## Tests and benchmark

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
./build/member3_fusion/member3_benchmark
```

The benchmark reports average/p95/p99 desktop latency for IMU prediction, GNSS update, AI-speed update, and the complete 100 Hz loop. Android performance is **NOT VALIDATED**.

## Known limitations

1. No delayed-measurement replay.
2. Local tangent-plane conversion is intended for vehicle-scale trajectories.
3. GNSS covariance is derived from HDOP because receiver covariance is not part of the current input contract.
4. Altitude is held at the reference fix because vertical position is not in the required 8-state model.
5. Quantitative blackout drift remains NOT VALIDATED without ground truth.
