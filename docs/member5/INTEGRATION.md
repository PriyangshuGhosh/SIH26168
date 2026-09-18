# Member 5 → Member 6 integration

Member 6 should depend only on:

1. `member5_engine/include/idr_engine_api.h`
2. The shared library (`libidr_engine.so` / `idr_engine.dll`)

Do not call FrameAligner, EKF, or MapMatchingEngine from Dart/Kotlin.

## Lifecycle

1. `idr_engine_init(map_db_path, onnx_model_path)` once after native load.
   - `map_db_path` may be a Member 4 **`.roadpack`** or a `maps/manifest.json` catalog (offline; no OSM at runtime).
   - After GNSS is available, call `idr_select_map_for_location(lat, lon)` (not from the 100 Hz IMU callback).
   - If the location is outside every provisioned region, `idr_map_status_message()` is `MAP DATA NOT AVAILABLE`.
   - `onnx_model_path` must be a real `speed_estimator.onnx` in production.
   - Tests may pass `"mock"` for speed only.
2. Stream IMU at **100 Hz** into `idr_feed_imu` (phone frame, m/s² and rad/s).
   Member 5 aligns with Member 2 and feeds Member 1 **at 100 Hz** (2 s / 200-sample windows).
3. Stream GNSS at ~1 Hz into `idr_feed_gnss` (skip this call to simulate a tunnel).
4. Poll `idr_get_current_state()` at ~10 Hz for the map marker.
5. Optional: `idr_get_road_segment_id()`, `idr_is_on_road_network()`, `idr_get_diagnostics()`.
6. `idr_engine_shutdown()` on app teardown.

Init return: **1 success, 0 failure**. On failure, `idr_engine_last_error()` has a short message.

## `IDRNavigationOutput`

| Field | Meaning |
|---|---|
| `timestamp` | Last processed sensor time (s) |
| `lat`, `lon` | WGS84, **map-matched** by Member 4 when on-network |
| `heading_deg` | Heading in degrees (snapped when on-network) |
| `speed_m_s` | Trusted speed (m/s) after the Member 5 validity layer. Canonical unit is m/s; UI km/h = m/s × 3.6 via `mpsToKmh`. If `idr_speed_is_valid()` is 0, Member 6 must show **Speed unavailable** rather than a cosmetic clamp. |
| `is_dead_reckoning` | `0` GNSS-aided, `1` dead reckoning |
| `confidence` | `[0,1]`, reduced in DR |

Struct layout of `IDRNavigationOutput` is unchanged from the original C ABI. Segment id / on-road are extra functions.

## Simulate GNSS outage

Stop calling `idr_feed_gnss`. After 1.2 s of IMU time, `is_dead_reckoning` becomes `1`. Feeding a fix with HDOP > 4 or fewer than 4 satellites also forces DR immediately.

## Dart FFI sketch

```dart
final dylib = DynamicLibrary.open('libidr_engine.so');
final init = dylib.lookupFunction<Int32 Function(Pointer<Utf8>, Pointer<Utf8>),
    int Function(Pointer<Utf8>, Pointer<Utf8>)>('idr_engine_init');
```

Map `IDRNavigationOutput` as a packed struct of six `double`s then `int` then `double` — **check alignment** (`int` may be followed by padding before `confidence` on some ABIs). Prefer a JNI wrapper that copies fields explicitly if FFI layout is uncertain.

## Threading

IMU and GNSS may be fed from different threads. Do not call `idr_feed_imu` from two IMU threads at once (SPSC). `idr_get_current_state` may be called from the UI thread.
