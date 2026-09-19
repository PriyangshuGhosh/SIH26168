# SIH26168 Member 6 — Expo Prototype PRD

## Summary
An Expo/React Native prototype that reproduces the Member 6 (Android integration/demo layer) behavior of the SIH26168 offline-navigation stack. Does **not** replace the authoritative native Kotlin + JNI + libmember5 Android project — it validates the NavigationState contract, safety guards, sensor pipeline math, and GNSS-outage UI so those pieces can be transferred to the native app.

## Scope
- Expo SDK 57 (Metro, React Native 0.86)
- Real device sensors via `expo-sensors` (accel/gyro) and `expo-location` (GNSS)
- JS Member 5 simulator (`MemberFiveEngine`) that mirrors the C ABI shape
- 4 screens: Navigation HUD, Diagnostics, Simulation, Validation Matrix
- FastAPI backend serving `.roadpack` region catalog (offline-safe)

## Non-goals
- Not a replacement for the native `libmember5.so` / JNI bridge
- Not a replacement for M1 ONNX / M3 EKF / M4 map-matcher
- Not a hardware-validated Android build

## Architecture
Sensors → SensorPipeline (timestamp-aware) → MemberFiveEngine (JS) → NavigationState → UI

## Validated behaviors (VALIDATED)
- NavigationState contract (types, units, validity bits, enums)
- Timestamp-aware IMU pairing (monotonic guard, stale/regression drops, nearest-ts pairing)
- Centralized SpeedGuard (rejects NaN/Inf/negative/absurd; never clamps)
- **700 km/h regression**: injecting 194.4 m/s → HUD renders "SPEED UNAVAILABLE" + reason
- Offline region selection (bounding-box, active-region cache, out-of-coverage detection)
- Backend `/api/roadpacks` + `/api/roadpacks/resolve` cross-checking

## Partial behaviors
- GNSS→DR mode transition (uses simple v_ENU propagation, not the real M3 EKF)
- GNSS recovery snaps to fresh fix; no covariance handoff
- expo-sensors ingestion works on device; web preview values are DOM DeviceMotion

## NOT VALIDATED
- Real Member 5 C ABI via JNI (`libmember5.so`)
- Real M1 ONNX speed model
- Real M2 alignment quaternion
- Real M3 EKF
- Real M4 `.roadpack` road-network snap-to-road
- arm64-v8a native library and APK packaging
- Physical Android hardware validation

## Test coverage
`src/__tests__/run.ts` — 24 tests covering SpeedGuard, RegionSelector, SensorPipeline. Run with `npx tsx src/__tests__/run.ts`.

## Files
- `frontend/src/navigation/types.ts` — NavigationState C ABI mirror
- `frontend/src/engine/MemberFiveEngine.ts` — JS simulator (MARKED NOT VALIDATED)
- `frontend/src/engine/EngineController.tsx` — provider wiring sensors→engine→UI
- `frontend/src/sensors/SensorPipeline.ts` — timestamp-aware pairing
- `frontend/src/safety/SpeedGuard.ts` — centralized m/s→km/h with rejection
- `frontend/src/maps/RegionSelector.ts` — offline region bounding-box selection
- `frontend/src/simulation/SyntheticDrive.ts` — dev-only synthetic scenarios
- `frontend/app/(tabs)/{index,diagnostics,simulation,docs}.tsx` — four screens
- `backend/server.py` — FastAPI region catalog
