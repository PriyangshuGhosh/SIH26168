# Member 6

Primary judging UI (Compose): [`../../app/`](../../app/). Lightweight shell: [`../../member6_mobile/README.md`](../../member6_mobile/README.md).

- JNI copies `IDRNavigationOutput` field-by-field (`IDRNavigationOutput` layout is unchanged).
- IMU timestamps: `SensorEvent.timestamp` nanoseconds → seconds; accel/gyro paired within 8 ms.
- Map catalog: `assets/maps/manifest.json` copied to `filesDir` (no `/sdcard` hard paths).
- Display: `mpsToKmh`; invalid speed → "Speed unavailable".
- Mock ONNX and GNSS-outage demo are labelled **SIMULATION**.
- Camera/vision is auxiliary and must not break IMU/GNSS navigation if it fails.

**ANDROID HARDWARE VALIDATION: NOT AVAILABLE** in this development environment.
**ANDROID PERFORMANCE: NOT VALIDATED**.

Roadpack matching data and any future MBTiles are separate artifacts. The checked-in catalog has one synthetic-grid region; out-of-region GNSS shows MAP DATA NOT AVAILABLE.
