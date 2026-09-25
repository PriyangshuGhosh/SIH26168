# Member 3 — Sensor Fusion

## Current completion status

**Status: IMPLEMENTED + HOST VALIDATED; real-driving validation remains open.**

### Confirmed in the repository

- Required 8-state EKF implementation is present:
  `[x, y, vx, vy, yaw, bax, bay, bgz]`.
- Member 3 consumes Member 2's aligned IMU contract rather than duplicating phone mounting alignment.
- GNSS position, optional GNSS speed, AI speed with variance, NHC, NIS/innovation gating, covariance handling, invalid-input handling, and timestamp policies are implemented.
- Python reference implementations are present.
- The latest host CTest run passed Member 3 C++ tests and both Python reference suites.
- A deterministic synthetic GNSS-blackout regression is included.

### Validation boundary

- The synthetic blackout regression is a repeatable sensor-bias test, not a real-driving accuracy result.
- The repository has no committed ground-truth driving log for quantitative 10/30/60/120 s real-driving drift.
- Android/arm64-v8a performance is **NOT VALIDATED**.

## State and interfaces

State order:

`x = [north_m, east_m, forward_m/s, lateral_m/s, yaw_rad, accel_bias_x, accel_bias_y, gyro_bias_z]ᵀ`

Public interface types are in `member3_fusion/include/member3/fusion_types.h`; the engine is declared in `EKFFusionEngine.hpp`.

## GNSS blackout evaluation

Dead reckoning continues without GNSS. The committed C++ regression uses a deterministic 20 s synthetic straight-line blackout with a fixed 0.03 m/s² accelerometer bias and checks drift against the known synthetic trajectory. This should not be presented as field accuracy.

## Build and test

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
./build/member3_fusion/member3_benchmark
```

## Downstream integration

Downstream code should include `member3/EKFFusionEngine.hpp` for the engine and may include `member3/fusion_types.h` for the public data contracts. The `sih26168::member3::NavigationState` contract is preserved for Member 4/5 consumers.

## Known limitations

1. No delayed-measurement replay or fixed-lag smoothing.
2. Local tangent-plane conversion is intended for vehicle-scale trajectories.
3. HDOP-to-metre conversion is a configurable approximation until receiver covariance is exposed.
4. Altitude is held at the reference GNSS fix because vertical position is not part of the required 8-state model.
5. Real-driving blackout drift and target-device performance require dedicated validation.
