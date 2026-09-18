# Member 6

Android navigation shell: [`../../member6_mobile/README.md`](../../member6_mobile/README.md).

- JNI copies `IDRNavigationOutput` field-by-field.
- IMU timestamps: `SensorEvent.timestamp` nanoseconds → seconds; accel/gyro paired within 8 ms.
- Map catalog: `assets/maps/manifest.json` copied to `filesDir` (no `/sdcard` hard paths).
- Display: `mpsToKmh`; invalid speed → "Speed unavailable".
- Debug builds: diagnostics panel.

Roadpack matching data and any future MBTiles are separate artifacts. The checked-in catalog has one synthetic-grid region; out-of-region GNSS shows MAP DATA NOT AVAILABLE.
