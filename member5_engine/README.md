# Member 5 — Edge Systems Engineer (`libidr_engine`)

Thread-safe native orchestrator that hosts Member 2 frame alignment, Member 1 speed inference (ONNX or mock), Member 3 fusion (stub until EKF lands), Member 4 map matching (stub), and the GNSS deficit state machine. Member 6 talks only to the C ABI in `include/idr_engine_api.h`.

## Pipeline

```text
idr_feed_imu (100 Hz, lock-free SPSC)
        |
        v
 Member 2 FrameAligner
        |
        +--> 2 s IMU window --> Member 1 speed (20 Hz stride)
        |
        v
 Member 3 fusion (stub EKF)  <--- idr_feed_gnss + deficit SM
        |
        v
 Member 4 map match (pass-through stub)
        |
        v
idr_get_current_state (poll ~10 Hz)
```

## C ABI

```c
int idr_engine_init(const char* map_db_path, const char* onnx_model_path); /* 1 = ok */
void idr_engine_shutdown(void);
void idr_feed_imu(double t, double ax, double ay, double az, double gx, double gy, double gz);
void idr_feed_gnss(double t, double lat, double lon, double alt, double speed, double hdop, int num_sats);
IDRNavigationOutput idr_get_current_state(void);
```

`idr_engine_init` returns **1 on success, 0 on failure** (same convention as the handbook stub).

Units: IMU m/s² and rad/s (phone frame). GNSS WGS84 degrees, speed m/s. Heading in the output is **degrees**.

## GNSS deficit state machine

Switch to dead reckoning when any of:

- HDOP > 4.0
- satellite count < 4
- no GNSS update for 1.2 s of **IMU/sensor time**

Quality failures update `is_dead_reckoning` on the calling thread (measured well under 10 ms on desktop; see `member5_benchmark`). Age-based outage is evaluated as IMU samples are processed.

## Build (desktop)

From the repository root:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -R member5 --output-on-failure -C Release
```

Outputs:

- Windows: `build/member5_engine/Release/idr_engine.dll` (or `build/member5_engine/idr_engine.dll`)
- Linux: `build/member5_engine/libidr_engine.so`

Optional ONNX Runtime (Member 1 `speed_estimator.onnx`):

```bash
cmake -S . -B build -DIDR_WITH_ONNXRUNTIME=ON -DIDR_ONNXRUNTIME_ROOT=/path/to/onnxruntime
```

Without ONNX, the engine uses the handbook mock: `v = max(0, mean(a_x) * 2)`, variance `0.05 m²/s²`.

## Android NDK (`arm64-v8a`)

Requires the Android NDK and a host CMake that can compile Member 2 (Eigen FetchContent needs network on first configure).

```bash
cmake -S . -B build-android \
  -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-24 \
  -DANDROID_STL=c++_shared \
  -DCMAKE_BUILD_TYPE=Release \
  -DSIH26168_BUILD_MEMBER5=ON

cmake --build build-android --target idr_engine -j
```

Copy `libidr_engine.so` plus `libc++_shared.so` into the Flutter/Kotlin `jniLibs/arm64-v8a/` folder. Header for FFI/JNI: `member5_engine/include/idr_engine_api.h`.

This NDK path is **not device-benchmarked** in this delivery.

## Integration notes

- `idr_feed_imu` / `idr_feed_gnss` are safe from the sensor threads. IMU uses a lock-free SPSC ring (capacity 2048). Use **one producer thread per queue**.
- Member 2 is not internally synchronized; the engine serializes `process` / `feedGnss` on the worker.
- `map_db_path` is accepted now and reserved for Member 4. Empty string is valid; matcher is pass-through.
- `onnx_model_path` is used only when `IDR_WITH_ONNXRUNTIME=ON` and the file exists; otherwise mock speed.
- Swap `StubFusionEngine` / `StubMapMatcher` for real Member 3/4 classes without changing the C ABI.

## Tests

| Target | What it covers |
|---|---|
| `member5_cpp_tests` | SPSC ring, deficit SM, C ABI, GNSS quality + stale-time DR, <10 ms quality switch |
| `member5_benchmark` | Mean `idr_feed_gnss` mode-switch latency |
| `member5_demo` | Short IMU+GNSS smoke print |
| `member5_synthetic_e2e` | Full-pipeline run on a synthetic 40 s tunnel drive; asserts DR entry/exit, drift, and map snap |

`member5_synthetic_e2e` must run with the repository root as the working directory (CTest
does this already) because it writes `member5_engine/tests/data/synthetic_e2e_log.csv`.

## Stubs vs real modules

| Slot | Current | Replace with |
|---|---|---|
| Member 1 | `MockSpeedEstimator` / optional ONNX | `speed_estimator.onnx` |
| Member 2 | **Real** `FrameAligner` | — |
| Member 3 | `StubFusionEngine` kinematic + NHC `v_y=0` | `EKFFusionEngine` |
| Member 4 | `StubMapMatcher` pass-through | `MapMatchingEngine` |
