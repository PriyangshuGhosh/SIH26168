# Member 2 — Integration for Members 1, 3, and 5

## C++ API

```cpp
#include "member2/FrameAligner.hpp"

using sih26168::member2::FrameAligner;
using sih26168::member2::FrameAlignerConfig;
using sih26168::member2::AlignedIMUFrame;
using sih26168::member2::CalibrationStatus;
using sih26168::member2::OptionalGnssAid;

FrameAlignerConfig cfg;           // all thresholds adjustable
FrameAligner aligner(cfg);
aligner.reset();

AlignedIMUFrame y = aligner.process(t, ax_p, ay_p, az_p, gx_p, gy_p, gz_p);

// Optional, calibration-only:
OptionalGnssAid gnss;
gnss.timestamp = t;
gnss.speed_mps = speed;
gnss.hdop = hdop;
gnss.num_sats = n;
aligner.feedGnss(gnss);
```

Link `member2_alignment` (CMake target `sih26168::member2`). Include path:
`member2_alignment/cpp/include`. Runtime: **no Python**.

Thread-safety: **not** internally synchronized. One aligner per stream; mutex if
IMU and GNSS are fed from different threads.

## Python reference

```python
from sih26168_alignment import FrameAligner, FrameAlignerConfig, OptionalGnssAid
aligner = FrameAligner(FrameAlignerConfig())
out = aligner.process(t, ax, ay, az, gx, gy, gz)
```

## Output `AlignedIMUFrame`

| Field | Content |
|---|---|
| `timestamp` | Echo of input time (s) |
| `ax_v..gz_v` | Vehicle-frame specific force (m/s²) and gyro (rad/s) |
| `q_pv[4]` | `[w,x,y,z]` phone→vehicle |
| `status` | `CalibrationStatus` |
| `confidence` | See `STATUS_AND_CONFIDENCE.md` |

When status is not `FULLY_ALIGNED`, vectors are still rotated by the **best available**
`R_vp` (identity or tilt-only). Downstream **must** read `status`.

## Member 1 (speed estimator)

- Consume **only** samples with `status == FULLY_ALIGNED` for training/inference of `v_x`, **or**
  train a degraded mode that uses gravity-aligned data with an explicit “yaw unknown” flag.
- Channel order after alignment: `[ax_v, ay_v, az_v, gx_v, gy_v, gz_v]` at **100 Hz** (no
  downsample). Member 5 packs a causal window of **T=200 samples (2 s)** as `[T, 6]` (ONNX
  `[B, T, 6]`); graphs that use handbook `[B, 6, T]` are transposed at load time.
- Inference stride in the engine is **10 samples** (10 Hz AI updates from the 100 Hz stream).
- Do not assume the first two seconds are static.
- If yaw is uncertain, `ax_v` is **not** guaranteed forward. Prefer gating on status.

## Member 3 (EKF/UKF)

- Prediction uses `ax_v, ay_v` and `gz_v` in the vehicle frame **when fully aligned**.
- If `YAW_UNCERTAIN` / `ROLL_PITCH_VALID`, do not apply non-holonomic `v_y≈0` as if axes were chassis-true; inflate IMU process noise or wait.
- `INVALID`: skip the measurement; do not integrate NaNs.
- GNSS used here is **navigation** GNSS; Member 2’s `feedGnss` is optional mount-aid using speed only. You may share speed, but Member 2 must keep working if you never call `feedGnss`.
- Quaternion is mount attitude, **not** vehicle heading in the world.

## Member 5 (native engine)

- Call `process` on the 100 Hz IMU thread (or serialize).
- Optionally call `feedGnss` when a quality speed is available; **must** still run if GNSS is dead (that is the product point).
- C ABI suggestion: wrap `process` inside `idr_feed_imu` **after** alignment, or expose aligned fields in the engine state.
- Do not heap-allocate per sample on top of the aligner; it already avoids that.
- `reset()` on session start and if the user is asked to remount/recalibrate.
- Android latency: **NOT VALIDATED** (no NDK device in this delivery). Desktop 100 Hz budget is measured by `member2_benchmark`.

## Mocks

While integrating, a mock must still emit `AlignedIMUFrame` with the same units and
`q_pv` layout. Identity `R_vp` is acceptable only if labelled `UNINITIALIZED` or if
the dataset is already in the vehicle frame.
