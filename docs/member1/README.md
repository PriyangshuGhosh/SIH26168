# Member 1 — ML / Speed Estimation

## Current completion status

**Status: PARTIAL — implementation pipeline exists, but the production model artifact and production validation are still missing.**

### Confirmed in the repository

- Windowing, dataset split, TCN/CNN model code, training/export scripts, and the production 100 Hz adapter are present under `member1-ml/`.
- The module exposes the intended speed-estimation pipeline for downstream integration.
- The repository explicitly keeps the restricted training dataset out of git.

### Still incomplete

- `speed_estimator.onnx` is **not present in the current checkout**.
- `data/member1_imu_speed.npz` is **not present in git**.
- Production 100 Hz accuracy against real 100 Hz IMU is **NOT VALIDATED**.
- The `mock` speed path used by Member 5 tests is simulation only and is not evidence of ML-model validation.

### Completion gate

Member 1 can be marked complete when the trained ONNX artifact is available, its ONNX/Python numerical-equivalence test is recorded, and the production 100 Hz evaluation report contains measured accuracy and robustness results.

## Documentation

See `member1-ml/docs/production_100hz.md` and `member1-ml/README.md` for the detailed model contract and validation procedure.
