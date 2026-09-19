# Member 6 — Android demonstration app

Kotlin + Jetpack Compose + JNI. Talks only to Member 5 `idr_engine_api.h` (Members 2–4 run inside `libidr_jni.so`). Road network data is Member 4 `.roadpack` / catalog, not map tiles.

## Build

```bash
cd member6_mobile
# ANDROID_HOME or local.properties sdk.dir
./gradlew clean assembleDebug testDebugUnitTest
```

ABI: **arm64-v8a**.

If `speed_estimator.onnx` is absent, the engine uses the explicit **mock** speed backend.

**REAL HARDWARE VALIDATION: NOT VALIDATED**
**ANDROID PERFORMANCE: NOT VALIDATED**
**SIH GNSS-denied accuracy: NOT VALIDATED**

## GNSS blackout demo

Toggle **Simulate GNSS outage** to stop `idr_feed_gnss`. `finalDriftMeters` is geodesic(estimated-at-restore, restored GPS), not last-GPS vs new-GPS.

V2V is **MODE A software simulation** (`kLibraryStatus`).
