# Member 1 status

Code lives in `member1-ml/`.

- Pipeline: windowing, splits, TCN/CNN, ONNX export scripts, 100 Hz production adapter.
- Dataset `data/member1_imu_speed.npz` is **not** in git.
- Trained `speed_estimator.onnx` is **not** in this checkout.
- Production 100 Hz accuracy against real 100 Hz IMU: **NOT VALIDATED** (see `member1-ml/docs/production_100hz.md`).
- Member 5 may use `onnx_model_path="mock"` only when explicitly requested; that path is **SIMULATION**.
