# Member 6 — Android navigation shell

Consumes **only** Member 5 `idr_engine_api.h` / `libidr_engine.so`.

## What this app does

1. Copies provisioned map assets into app-controlled storage (`filesDir`). No `/sdcard/...` developer paths.
2. Reads GNSS (when available) and selects a **local** `.roadpack` from `assets/maps/manifest.json` by WGS84 bounds.
3. Streams IMU at ~100 Hz after **timestamp-aware accel/gyro pairing** (`SensorEvent.timestamp` nanoseconds → seconds).
4. Polls `idr_get_current_state()` at ~10 Hz.
5. Converts speed with `mpsToKmh` (`× 3.6`). Invalid upstream speed is shown as **Speed unavailable**, not a fake 120 km/h.
6. If the fix is outside every provisioned region: **MAP DATA NOT AVAILABLE** / Offline map unavailable for this area.
7. Debug builds show a diagnostics panel (GNSS/AI/EKF/display speed, reject reason, map status, IMU Hz).

## What it does not do

- Download OSM during GNSS-denied runtime.
- Treat MBTiles as a Member 4 roadpack (tiles are rendering-only; this demo uses a bounds-aware canvas plus the roadpack).
- Claim a worldwide offline map. The checked-in catalog currently has **one** synthetic-grid region.

## Build

Host C++ tests (no device):

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build -R 'member3|member4|member5' --output-on-failure
```

Android (requires SDK/NDK):

```bash
# 1) Cross-compile libidr_engine.so
./member5_engine/scripts/build_android_arm64.sh
# 2) Copy into jniLibs (or let Gradle pick NDK cmake if configured)
# 3)
cd member6_mobile
./gradlew assembleDebug
```

**ANDROID HARDWARE VALIDATION:** not claimed by this repository's CI.

## GNSS blackout demo

Toggle **Simulate GNSS outage** to stop `idr_feed_gnss`. The already-selected roadpack stays loaded. Restore GNSS to resume aiding.
