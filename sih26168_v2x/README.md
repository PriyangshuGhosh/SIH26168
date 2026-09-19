# SIH26168 V2X cooperative localization (MODE A)

**MODE A — SOFTWARE SIMULATION ONLY.**

This is a standalone library. It does **not** receive C-V2X/5.9 GHz radio.
A phone cannot ingest AIS-230/C-V2X natively. There is **no OBU driver**,
**no USB/Bluetooth adapter**, and **no Android hardware integration**.

Status labels:

| Claim | State |
|---|---|
| C++ core, Python oracle, simulator, replay, tests | **IMPLEMENTED** (host) |
| Cooperative measurement + covariance + NIS gating | **IMPLEMENTED** (host) |
| Real V2X / OBU / C-V2X / NR-V2X | **NOT IMPLEMENTED**, **NOT VALIDATED** |
| Android radio/JNI | **DESIGNED** only |
| Member 3 EKF wiring | **DESIGNED** (`member3_adapter.hpp`), not linked |
| Camera / depth | **NOT PRESENT** (dropped) |

## Layout

```text
sih26168_v2x/
  include/sih26168/v2x/   C++ public API
  src/                    C++20 core
  python/sih26168_v2x/    mathematical oracle + simulator
  tests/                  C++ and pytest
  docs/                   architecture and math
```

CMake target: `sih26168::v2x`

## Build / test

Standalone:

```bash
cmake -S sih26168_v2x -B build-v2x -DCMAKE_BUILD_TYPE=Release
cmake --build build-v2x -j
ctest --test-dir build-v2x --output-on-failure
./build-v2x/sih26168_v2x_benchmark
```

From the SIH26168 root (optional `SIH26168_BUILD_V2X=ON`, default ON):

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target sih26168_v2x_tests
ctest --test-dir build -R sih26168_v2x --output-on-failure
PYTHONPATH=sih26168_v2x/python python3 -m pytest sih26168_v2x/tests/python -q
PYTHONPATH=sih26168_v2x/python python3 -m sih26168_v2x.experiments
```

## Public API (conceptual)

```cpp
sih26168::v2x::V2XCore core(cfg);
core.lockOrigin(origin);
core.ingest(normalized_message);           // or pollTransport()
auto r = core.getCooperativeMeasurement(local_nav_state);
// r.decision: Accept / Downweight / Reject / Unavailable
```

V2X is optional. Zero remotes → `Unavailable` / `no_v2x`. Navigation continues.

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [V2X_MESSAGE_MODEL.md](docs/V2X_MESSAGE_MODEL.md)
- [COOPERATIVE_LOCALIZATION.md](docs/COOPERATIVE_LOCALIZATION.md)
- [SIMULATION.md](docs/SIMULATION.md)
- [SECURITY.md](docs/SECURITY.md)
- [BENCHMARKS.md](docs/BENCHMARKS.md)
- [HARDWARE_INTEGRATION.md](docs/HARDWARE_INTEGRATION.md) (designed, not validated)
- [ANDROID_INTEGRATION.md](docs/ANDROID_INTEGRATION.md) (designed, not implemented)
