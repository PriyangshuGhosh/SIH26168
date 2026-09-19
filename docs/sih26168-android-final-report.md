# SIH26168 Android demonstration — final report

This is an engineering status report. Unverified items are **NOT VALIDATED**.

**REAL HARDWARE VALIDATION: NOT VALIDATED**  
**SIH GNSS-denied accuracy: NOT VALIDATED** (no closed-course experiment on this run)

## 16-point checklist

| # | Item | Status |
|---|---|---|
| 1 | Kotlin / Jetpack Compose / ViewModel / StateFlow / coroutines / JNI | Implemented (host unit tests; device UI **NOT VALIDATED**) |
| 2 | Original Maps-like canvas (no Google branding/assets) | Implemented (Canvas roads + HUD). Not a Google Maps SDK |
| 3 | Offline Member 4 roadpack catalog | Bundled synthetic + OSM extract; `idr_engine_init(manifest)` |
| 4 | No internet required for matching | Match path is local JNI + roadpack. Outage demo withholds GNSS |
| 5 | Explicit navigation modes | `NavigationMode` labels in HUD |
| 6 | GNSS outage tracker | `OutageTracker` |
| 7 | `finalDriftMeters` = geodesic(estimated-at-restore, restored GPS) | Unit-tested; **not** last-GPS vs new-GPS |
| 8 | Engineering dashboard | Raw GNSS vs AI vs EKF vs displayed speed |
| 9 | Outage history | List + last drift |
| 10 | Trajectory visualization | GPS trail vs estimate trail on canvas |
| 11 | V2V | JNI to existing `V2XCore` simulated transport. **MODE A SIMULATION**. Radio **NOT VALIDATED** |
| 12 | Speed/position validation | Invalid speed → “Speed unavailable”; raw GNSS shown separately |
| 13 | Lifecycle / permissions | Sensors onStart/onStop; FINE/COARSE location |
| 14 | Thread-safe JNI POD | Mutex + field copies, not packed-struct FFI |
| 15 | Logging / replay / experiment | JSONL logger + `ReplayParser` / `FakeEnginePort` e2e unit test |
| 16 | `assembleDebug` arm64-v8a + unit tests | See build log for this PR. Device run **NOT VALIDATED** |

## What was not claimed

- No sub-metre GNSS-denied accuracy.
- No C-V2X/OBU.
- No live Overpass-from-phone download (Member 4 host pipeline exists).
- Member 1 ONNX on device only if a real `speed_estimator.onnx` is provisioned; otherwise **mock**.

## APIs used

Member 6 → Member 5 `idr_engine_api.h` only for navigation. Member 4 matcher is not called from Kotlin. V2V uses `sih26168::v2x::V2XCore`.
