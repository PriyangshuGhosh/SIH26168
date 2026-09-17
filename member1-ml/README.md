# SIH26168 — Member 1: IMU-only vehicle speed estimation

This repo estimates vehicle speed (m/s) from 6-axis smartphone IMU data (accelerometer + gyroscope, 10 Hz). Its output feeds
Member 3's adaptive EKF/UKF for intelligent dead reckoning, via an ONNX graph Member 5 integrates in a C++20 + ONNX Runtime
application.

**Status: all four milestones are done.** 1 (data foundation + baselines), 2 (causal CNN/TCN point estimators),
3 (heteroscedastic uncertainty, augmentation-policy selection, robustness, final model), 4 (inference contract, ONNX
export + verification, CPU edge benchmark, final leakage/causality audit). The one deliberately unimplemented item
is a *retrained-per-fold* LOVO benchmark (the fold machinery exists in `src/data/splits.py::lovo_folds`; running it
means training one model per held-out vehicle family, out of scope for this deployment-focused final milestone).

The final model (CNN, 4 s window, yaw-only rotation augmentation, heteroscedastic uncertainty head) reaches a test MAE
of 4.79 m/s (17.2 km/h), exports to a 127 KB ONNX graph verified against PyTorch to within 2e-5 max abs error, and runs
at ~0.32 ms/window (single-threaded CPU, ONNX Runtime) — see [`docs/experiments.md`](docs/experiments.md) for the full
picture, including why "yaw" augmentation was chosen over full SO(3) or none, and an honest calibration result: the
model's uncertainty is directionally useful but **overconfident on the held-out test trips** (see "Known limitations"
below).

## Quick start

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128   # or the CPU wheel
pip install -r requirements.txt
# place the dataset at data/member1_imu_speed.npz (not tracked)
python -m src.data.inspect_dataset          # dataset summary + validation
python -m pytest                            # tests (synthetic fixtures; real-data contract test if the NPZ exists)
python scripts/run_baselines.py             # baselines -> results/baselines/
python scripts/run_training.py              # CNN/TCN x 2s/4s point models -> experiments/, results/neural/
python scripts/run_training.py --no-so3 --tag m2abl_noso3 --results-dir results/neural_ablation_no_so3  # M2 ablation
python scripts/run_uncertainty.py           # M3: uncertainty + augmentation selection + robustness + final model
python scripts/export_onnx.py               # M4: export the final checkpoint to ONNX + verify + benchmark
python scripts/run_evaluation.py            # M4: reproduce the final checkpoint's val/test/unseen-group metrics (no retraining)
python scripts/run_ablation.py              # M4: consolidate the M2/M3 ablations already run into one table
```

## Production flow

```
6-axis smartphone IMU (acc + gyr, 10 Hz)
  -> causal windowing (2 s / 4 s) + normalization (fitted on training data, baked into the checkpoint)
  -> causal CNN (VelocityNet, 27,266 parameters)
  -> velocity_mps + uncertainty (heteroscedastic) + confidence, via predict_contract (PyTorch) or the exported ONNX graph
  -> timestamp attached by the caller
  -> Member 3's adaptive EKF/UKF (fusion logic is Member 3's responsibility, not implemented here)
```

## Known limitations

- **Test-set uncertainty is overconfident.** Observed coverage falls below the nominal level at every confidence band
  on the S-series test set (e.g. ~47% of test points land inside the predicted 1-sigma interval, against the 68% a
  well-calibrated Gaussian would give). `uncertainty`/`confidence` are directionally useful (they do correlate with
  error) but should not be treated as a precisely-calibrated Gaussian interval. See `docs/experiments.md` (Milestone 3
  calibration section) and `docs/member1_output_contract.md`.
- **No input-noise-robust training.** Sensor noise and vibration are the largest perturbations tested in the M3
  robustness battery; the model was not trained with noise augmentation to counter them.
- **LOVO (retrained-per-fold) is not implemented**, per above.

## Documentation

- [`docs/data_protocol.md`](docs/data_protocol.md): dataset structure, allowed and forbidden inputs, target, windowing, splits, augmentation
- [`docs/architecture.md`](docs/architecture.md): modules, tensor contract, baseline/model/uncertainty methods, ONNX export and edge benchmark
- [`docs/experiments.md`](docs/experiments.md): results for every milestone and how to reproduce them
- [`docs/member1_output_contract.md`](docs/member1_output_contract.md): the `velocity_mps`/`uncertainty`/`confidence`/`timestamp` schema for Member 3, and the ONNX graph that also produces it
