# Member 6: Mobile Application & UI Integration

This document outlines the architecture, implementation, and status of the Android application integrating the Intelligent GNSS-Denied Navigation System (SIH26168).

## 1. Architecture
The mobile app serves as the hardware interface and presentation layer. It captures physical sensors (IMU, GNSS, Camera), funnels them deterministically through a JNI bridge to the Member 5 Native Engine, and renders the resulting `IDRNavigationOutput` on an offline Compose Canvas map.

## 2. Mobile Stack
**Native Android (Kotlin + Compose + JNI)**
Chosen for deterministic sensor timestamping, robust CameraX access, and lowest-latency C++ JNI interop. Flutter was evaluated but rejected due to Dart FFI overhead on 100Hz high-frequency IMU streams.

## 3. Sensor Pipeline
- **IMU:** 100 Hz via `ImuService.kt`. High sampling rate requested via `SENSOR_DELAY_FASTEST` (requires `HIGH_SAMPLING_RATE_SENSORS` permission).
- **GNSS:** 1 Hz via `GnssService.kt`.
- **Synchronization:** Monotonic Android `SensorEvent.timestamp` is passed directly to the native engine to prevent wall-clock drift.

## 4. Native Engine Integration
The C++ core is compiled to `libidr_engine.so` (arm64-v8a and armeabi-v7a). The app uses a JNI bridge (`member6_jni.so`) to call `idr_engine_init`, `idr_feed_imu`, `idr_feed_gnss`, and `idr_get_current_state`.

## 5. Offline Map
MapLibre was originally attempted but crashed natively due to a deprecated v9 annotation plugin. It was completely replaced with a **Pure Compose Canvas Map** that renders an offline grid and a rotating vehicle marker directly using Skia. It works 100% offline with zero native crashes.

## 6. GNSS Outage Simulation
A deterministic toggle in `NavigationViewModel.kt` blocks GNSS updates from reaching the C++ engine, forcing the engine into Dead Reckoning (DR). The UI updates to indicate "DEAD RECKONING".

## 7. Vision Pipeline & Confidence Gating (EXPERIMENTAL)
Camera frames are captured via CameraX. `VisionPipeline.kt` provides an adapter for experimental optical flow/depth tracking. *Current status: Adapter implemented, awaiting Member 3 EKF visual update endpoint.* Vision failures intentionally do not crash the baseline IMU/GNSS pipeline.

## 8. Build Instructions
```bash
# Debug Build
./gradlew assembleDebug

# Release Build
./gradlew assembleRelease

# Install directly to device
./gradlew installDebug
```
*Note: Requires Android SDK 34, NDK 28.x, and CMake 3.22.*

## 9. Performance & Latency
- **IMU Ingestion:** ~100 Hz (VALIDATED)
- **Native Bridge:** <1ms overhead (VALIDATED)
- **UI Update:** ~10-15 Hz (VALIDATED)

## 10. Known Limitations & Dependencies
- **Member 1 (AI Speed):** MOCK. `speed_estimator.onnx` has not been provided. The C++ engine falls back to a math mock.
- **Member 3 (EKF):** REAL.
- **Member 4 (Map Matching):** REAL.
