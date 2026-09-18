# Member 5 documentation

- Engine usage, ABI, Android NDK, production vs mock: [`../../member5_engine/README.md`](../../member5_engine/README.md)
- Binding the C ABI from the mobile app: [`INTEGRATION.md`](INTEGRATION.md)

Production pipeline: 100 Hz IMU → Member 2 `FrameAligner` → Member 1 ONNX at **100 Hz** (200-sample / 2 s window, stride 10; or explicit mock) → Member 3 `EKFFusionEngine` → Member 4 `MapMatchingEngine` → C ABI.
