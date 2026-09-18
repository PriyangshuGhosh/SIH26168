# Member 5 — Edge Systems Engineer (`libidr_engine`)

Thread-safe native orchestrator:

`raw IMU → Member 2 FrameAligner → Member 1 speed (ONNX, or explicit mock) → Member 3 EKF → Member 4 MapMatchingEngine (.roadpack) → C ABI`

Member 6 talks only to `include/idr_engine_api.h`. There is no production `StubFusionEngine` or `StubMapMatcher`.

## Pipeline

```text
idr_feed_imu (100 Hz, lock-free SPSC)
        |
        v
 Member 2 FrameAligner
        |
        +--> 2 s / 200-sample 100 Hz window --> Member 1 speed (stride 10)
        |
        v
 Member 3 EKFFusionEngine  <--- idr_feed_gnss + deficit SM
        |
        v
 Member 4 MapMatchingEngine (offline .roadpack HMM)
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
long long idr_get_road_segment_id(void);
int idr_is_on_road_network(void);
```

`idr_engine_init` returns **1 on success, 0 on failure**. On failure, `idr_engine_last_error()`.

Units: IMU m/s² and rad/s (phone frame). GNSS WGS84 degrees, speed m/s. Output heading is **degrees**. Matched lat/lon/heading/confidence come from Member 4 when the fix is on-network; segment id and on-road flag are extra C getters so the original `IDRNavigationOutput` layout is unchanged.

## Production vs mock

- **Map:** `map_db_path` must be an existing Member 4 `.roadpack`. GraphML/GeoJSON are offline **build** inputs (Python tools), not the C++ runtime format. Empty path, `mock:`, or a corrupt pack fails init.
- **Speed:** production requires `speed_estimator.onnx` and a build with `-DIDR_WITH_ONNXRUNTIME=ON`. Missing model **fails init** (no silent mock).
- **Explicit mock (tests/dev only):** `onnx_model_path` of `"mock"` / `"mock:..."`, or `SIH26168_ALLOW_MOCK_SPEED=1`.

Default desktop builds in this repo often have **no ONNX Runtime linked**. End-to-end CTest therefore uses `"mock"` on purpose; that is labelled, not a production fallback.

## GNSS deficit state machine

Switch to dead reckoning when any of:

- HDOP > 4.0
- satellite count < 4
- no GNSS update for 1.2 s of **IMU/sensor time**

Quality failures update `is_dead_reckoning` on the calling thread. Age-based outage is evaluated as IMU samples are processed.

Member 3 additionally gates GNSS measurement quality (stricter HDOP/sats inside the EKF). The deficit SM still owns the DR flag on the C ABI.

## Build (desktop)

From the repository root:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -R 'member2|member3|member4|member5' --output-on-failure -C Release
./build/member2_alignment/member2_benchmark
./build/member5_engine/member5_benchmark
./build/member5_engine/member5_synthetic_e2e
```

Linux output: `build/member5_engine/libidr_engine.so`

Optional ONNX Runtime:

```bash
cmake -S . -B build -DIDR_WITH_ONNXRUNTIME=ON -DIDR_ONNXRUNTIME_ROOT=/path/to/onnxruntime
```

Place Member 1’s exported graph at the path passed to `idr_engine_init`.

**Member 1 live rate is 100 Hz.** The engine does **not** downsample aligned IMU. It packs
`[T, 6]` time-major windows (`T` from the ONNX graph, default **200 = 2 s**) with channels
`[ax, ay, az, gx, gy, gz]`. ONNX input `[B, T, 6]` (Member 1 `export_onnx.py`) is the default;
`[B, 6, T]` (handbook) is detected and filled by transpose. Outputs follow the Member 1 contract
(`velocity_mps`, `uncertainty` as sigma → variance for Member 3, `confidence`) and also accept
handbook names `estimated_velocity` / `velocity_variance`.

The in-tree `member1-ml` training config still documents a 10 Hz NPZ (`sample_rate_hz: 10.0`,
windows 20/40). That is the **training-dataset** description. Production ingestion follows the
**100 Hz** live contract (user + handbook 200-sample / 2 s window). A leftover 10 Hz-trained graph
with T=20/40 would see 0.2/0.4 s of 100 Hz data — export a 100 Hz `speed_estimator.onnx` with T=200
(or 400) before claiming numerical parity.

## Android NDK (`arm64-v8a`)

```bash
export ANDROID_NDK=/path/to/ndk
bash member5_engine/scripts/build_android_arm64.sh
```

**ANDROID PERFORMANCE: NOT VALIDATED** (no device in this delivery). Cross-build only when NDK is present.

## Tests

| Target | What it covers |
|---|---|
| `member5_cpp_tests` | SPSC, deficit SM, production error paths, C ABI, GNSS dropout, real M4 vs stub ids, M2→M3 contract |
| `member5_benchmark` | GNSS mode-switch latency **and** 100 Hz pipeline feed timing (measured) |
| `member5_demo` | Short IMU+GNSS smoke print |
| `member5_synthetic_e2e` | 30 s synthetic tunnel on `synthetic_grid.roadpack` with real M2/M3/M4 |

CTest working directory is the repository root so the synthetic `.roadpack` resolves.

## Threading

`idr_feed_imu` / `idr_feed_gnss` are safe from the sensor threads. IMU uses a lock-free SPSC ring (capacity 2048). One producer thread per queue. Member 2/3/4 run on the engine worker.
