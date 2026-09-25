# Member 6 — Mobile Application & UI

## Current completion status

**Status: IMPLEMENTED IN REPOSITORY; APK CI and hardware validation are not yet confirmed.**

### Confirmed in the repository

- Android navigation code is present under `member6_mobile/`.
- JNI copies the native navigation output field-by-field.
- Phone IMU timestamp conversion and accelerometer/gyroscope pairing logic are documented.
- Offline map catalog handling uses app storage rather than hard-coded `/sdcard` paths.
- Speed display converts m/s to km/h and handles invalid speed explicitly.
- A diagnostics panel is available in debug builds.

### Current validation boundary

- The latest Android APK workflow did **not reach the APK build step**: it failed during the Android SDK setup step.
- Therefore, the repository does not currently have a successful CI-verified APK build from this latest run.
- Hardware installation, sensor streaming, native-engine integration on a phone, offline map behavior, and repeatable GNSS-outage demonstration remain **NOT VALIDATED** by this repository status.

### Integration contract

Member 6 should depend on:

1. `member5_engine/include/idr_engine_api.h`
2. `libidr_engine.so`

Do not call Member 2/3/4 internals directly from the UI layer.

## Documentation

See [member6_mobile/README.md](../../member6_mobile/README.md) for the Android build and integration details.
