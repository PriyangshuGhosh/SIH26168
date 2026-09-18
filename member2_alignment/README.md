# SIH26168 — Member 2 Frame Alignment

Production module: **Sensor Calibration & Coordinate Frame Alignment**.

Phone IMU (arbitrary mount) is converted into the vehicle frame:

- **+X** forward  
- **+Y** left  
- **+Z** up  

Quaternion `q_pv` is Hamilton **`[w, x, y, z]`** and rotates vectors **phone → vehicle**.

**Gravity determines roll/pitch but not absolute yaw.** Yaw is estimated only from
reliable longitudinal motion evidence (optional GNSS speed-rate as calibration aid).

## Layout

```text
member2_alignment/
├── python/sih26168_alignment/   # reference implementation
├── cpp/include/member2/         # FrameAligner.hpp, calibration_types.h
├── cpp/src/FrameAligner.cpp
├── cpp/tools/                   # CSV driver + benchmark
└── tests/
```

## Build / test / benchmark

```bash
python3 -m pip install -r member2_alignment/requirements.txt
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
PYTHONPATH=member2_alignment/python python3 -m pytest -q
PYTHONPATH=member2_alignment/python python3 member2_alignment/python/generate_test_vectors.py
./build/member2_alignment/member2_benchmark
```

If Eigen3 is not installed, CMake fetches Eigen 3.4.0 headers.

## Downstream API

```cpp
#include "member2/FrameAligner.hpp"
sih26168::member2::FrameAligner aligner(config);
aligner.reset();
auto out = aligner.process(t, ax_p, ay_p, az_p, gx_p, gy_p, gz_p);
```

See `docs/member2/` for conventions, algorithm, confidence semantics, and Member 1/3/5 handoff.

C++ tests cover 100 Hz streams, jitter, dropped samples, duplicates, out-of-order timestamps, invalid samples, long-stream determinism, and Member 1 **100 Hz** window packing (`[T=200, 6]` over 2 s, no downsample). Recorded-phone accuracy remains **NOT VALIDATED** until a log is placed in `tests/data/recorded/`. Desktop `member2_benchmark` measures per-frame time; Android is **NOT VALIDATED**.
