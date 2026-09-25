# Member 5 — Native Edge Engine

## Current completion status

**Status: INTEGRATED + BUILD VALIDATED; synthetic end-to-end gate is currently failing.**

### Confirmed in the repository

- Native C++ engine builds successfully on the host.
- Member 5 C++ regression tests pass.
- Member 5 benchmark passes.
- The production architecture integrates Member 2 alignment, Member 3 fusion, Member 4 map matching, and the Member 5 C ABI.
- The engine supports an explicit mock speed backend for deterministic simulation tests.

### Current blocking validation

The latest host CTest run completed **11/12 tests successfully**; the only failing test is `member5_synthetic_e2e`.

At the 22 s point in the synthetic tunnel:

- DR mode is active.
- Mock speed is only **0.0147 m/s**.
- North progress is **-79.59 m** relative to the expected forward motion.
- Reported position error is **135.59 m**, exceeding the test's 80 m threshold.

The failure is in the synthetic/mock DR path. It must be fixed before the complete Member 5 end-to-end gate can be marked passed. The test threshold should not simply be relaxed.

### Production boundary

- A real trained ONNX artifact is not present in the current checkout, so the real ML inference path is not validated here.
- Android/arm64-v8a performance and target-device latency are not established by the current host test.
- Do not present the mock backend or synthetic trajectory as field validation.

## Documentation

- Engine usage, ABI, Android NDK, production vs mock: [Member 5 engine README](../../member5_engine/README.md)
- Member 5 → Member 6 handoff: [INTEGRATION.md](INTEGRATION.md)

Production pipeline:

`100 Hz IMU → Member 2 FrameAligner → Member 1 ONNX/mock → Member 3 EKF → Member 4 MapMatchingEngine → C ABI`
