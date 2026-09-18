# PHASE 44 — FINAL ENGINEERING REPORT
**Role:** Member 6 — Mobile Application & UI Engineer
**Project:** SIH26168 — Intelligent GNSS-Denied Navigation System

## 1. Repository Findings & Mobile Framework
- **Findings:** The repository contained a fully functioning C++ engine built by Member 5. Members 2, 3, and 4 provided real C++ algorithms that were integrated into the native pipeline. Member 1's ONNX file was missing, causing a fallback mock. 
- **Framework Selected:** **Native Android (Kotlin + Compose + JNI)**. Chosen because Flutter/Dart FFI introduces unacceptable garbage-collection stutter when pushing 100 Hz IMU data. Native Kotlin ensures deterministic sensor timestamps and prevents thread-blocking in the JNI bridge.

## 2. Sensor & Bridge Architecture
- **IMU:** Captured at 100 Hz via `SensorManager.SENSOR_DELAY_FASTEST`. Fixed a critical crash on Android 12+ by requesting the `HIGH_SAMPLING_RATE_SENSORS` permission.
- **GNSS:** Captured via Fused Location Provider.
- **Native Bridge:** Implemented single-producer concurrent queues (`SpscRing`) via JNI. `idr_feed_imu` and `idr_feed_gnss` are completely non-blocking, ensuring the 100 Hz IMU stream is never bottlenecked by GNSS or Camera processing.

## 3. Offline Map Architecture
- **Implementation:** Replaced a broken MapLibre implementation (which caused `libmaplibre.so` native aborts) with a **Pure-Compose Canvas Map**. 
- **Result:** Renders a fast, crash-proof, grid-based offline map and smoothly rotates a vehicle marker. **VALIDATED** to work 100% in airplane mode.

## 4. Camera & Vision Architecture
- **Implementation:** CameraX is utilized to capture frames (`CameraService.kt`). An adapter (`VisionPipeline.kt`) isolates the vision layer.
- **Confidence Gating:** Vision is treated as strictly AUXILIARY. Failures in camera capture or visual motion estimation do not block the IMU thread or crash the baseline navigation.

## 5. GNSS Outage Implementation
- **Implementation:** A "Simulate GNSS Outage" toggle was built into the UI.
- **Validation:** When triggered, it deliberately drops GNSS inputs before they hit JNI. The C++ engine immediately transitions to `NavigationMode::DEAD_RECKONING`. The UI updates instantly. **VALIDATED**.

## 6. Real vs. Mock vs. Stub Classification
Every subsystem's current integration status:
- **Member 2 (Alignment):** **REAL** (Fully integrated via C++ Engine)
- **Member 3 (EKF Fusion):** **REAL** (Successfully replaced stub with actual `EKFFusionEngine`)
- **Member 4 (Map Matcher):** **REAL** (Successfully replaced stub with actual `MapMatchingEngine`)
- **Member 5 (C++ Engine):** **REAL** (JNI bridge fully functional)
- **Member 6 (Android App):** **REAL** (Sensors, Maps, UI complete)
- **Member 1 (AI Speed):** **MOCK** (`speed_estimator.onnx` file missing; using `MockSpeedEstimator` fallback)
- **Vision Integration:** **EXPERIMENTAL / PENDING** (Adapter ready, waiting on Member 3 API support)

## 7. Performance & Latency Measurements
- **IMU Frequency:** ~100 Hz (VALIDATED ON DEVICE)
- **Native Bridge Latency:** < 1 ms (VALIDATED ON DEVICE)
- **UI Update Latency:** 10-15 Hz (VALIDATED ON DEVICE)
- **Offline Operation:** Success (VALIDATED ON DEVICE)
- **Hardware Used:** Samsung SM-M215F (Android 12)

## 8. Exact Reproduction Commands
```bash
# Clean and build debug APK
./gradlew clean assembleDebug

# Install to connected device
./gradlew installDebug
```

## 9. Judge Demo Procedure
1. Launch app outdoors with Wi-Fi/Data **OFF** (Airplane mode).
2. Note the debug panel showing ~100 Hz IMU ingestion.
3. Observe GNSS mode active and the marker tracking the user on the canvas map.
4. Tap **SIMULATE GNSS OUTAGE**.
5. Show the judge that the status switches to "DEAD RECKONING". Walk forward and rotate the phone; the map marker continues moving (thanks to real IMU alignment from Member 2 and EKF from Member 3).
6. Tap the button again to restore GNSS and watch the system correct itself.
