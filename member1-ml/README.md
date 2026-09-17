# SIH26168 — Member 1: IMU-only vehicle speed estimation

This repo estimates vehicle speed (m/s) from 6-axis smartphone IMU data (accelerometer + gyroscope, 10 Hz). Its output feeds
Member 3's adaptive EKF/UKF for intelligent dead reckoning, via an ONNX graph Member 5 integrates in a C++20 + ONNX Runtime
application.

**Status: all four milestones are done.** 1 (data foundation + baselines), 2 (causal CNN/TCN point estimators),
3 (heteroscedastic uncertainty, augmentation-policy selection, robustness, final model), 4 (inference contract, ONNX
export + verification, CPU edge benchmark, final leakage/causality audit). The one deliberately unimplemented item
is a *retrained-per-fold* LOVO benchmark (the fold machinery exists in `src/data/splits.py::lovo_folds`; running it
means training one model per held-out vehicle family, out of scope for this deployment-focused final milestone).

**Two checkpoints exist now, honestly reporting two different numbers -- neither hides the other:**

| Use | Checkpoint | Window | Test MAE | ONNX | CPU latency (single-threaded ONNX Runtime) |
|---|---|---|---|---|---|
| Non-production / offline (milestone-3 selection, best accuracy) | `experiments/m3_final_cnn_w40` | 4 s @ 10 Hz | **4.79 m/s** (17.2 km/h) | 127 KB | ~0.32 ms/window |
| Production (matches the 100 Hz / 200-sample Member 2 contract) | `experiments/production_cnn_w20` | 2 s @ 10 Hz, decimated from 200 @ 100 Hz | **5.14 m/s** (18.5 km/h) | 127 KB native / 130 KB production graph | ~0.09 ms/window (production graph) |

Both: CNN, yaw-only rotation augmentation, heteroscedastic uncertainty head, verified against PyTorch to
within ~1.2e-4 max abs error. See [`docs/experiments.md`](docs/experiments.md) for the w40 milestone-3
picture (why "yaw" augmentation was chosen over full SO(3) or none) and
[`docs/production_100hz.md`](docs/production_100hz.md) for why the production path uses the smaller,
less-accurate w20 checkpoint (the contract specifies a 2-second window; the milestone-3 winner used 4).
Both models share the same known calibration limitation: uncertainty is directionally useful but
**overconfident on the held-out test trips** (see "Known limitations" below).

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

The model is trained and evaluated on the project's real dataset, which is natively 10 Hz -- no
genuine 100 Hz IMU recording exists to train on (see
[`docs/production_100hz.md`](docs/production_100hz.md)). Two input paths reach the same model and the
same output contract:

```
# Evaluation / offline path (this repo's own dataset, 10 Hz)
6-axis smartphone IMU (acc + gyr, 10 Hz)
  -> causal windowing (2 s / 4 s) + normalization (fitted on training data, baked into the checkpoint)
  -> causal CNN (VelocityNet, 27,266 parameters)
  -> velocity_mps + velocity_variance_m2s2 (heteroscedastic) + confidence, via predict_contract (PyTorch) or the exported ONNX graph
  -> timestamp attached by the caller
  -> Member 3's adaptive EKF/UKF (fusion logic is Member 3's responsibility, not implemented here)

# Production path (Member 2's genuine 100 Hz AlignedIMUFrame stream)
Member 2 AlignedIMUFrame (ax_v..gz_v, 100 Hz, status-gated on FULLY_ALIGNED)
  -> ProductionWindowBuffer: causal 200-sample (2 s) raw buffer (src/inference/member2_interface.py)
  -> decimate to the model's native 10 Hz resolution (20 samples) -- real samples kept, never interpolated
  -> the SAME causal CNN (window=20 checkpoint only)
  -> velocity_mps + velocity_variance_m2s2 + confidence + timestamp, via predict_contract_production or export_production_model's ONNX graph
  -> Member 3's adaptive EKF/UKF
```

## Known limitations

- **Test-set uncertainty is overconfident.** Observed coverage falls below the nominal level at every confidence band
  on the S-series test set (e.g. ~47% of test points land inside the predicted 1-sigma interval, against the 68% a
  well-calibrated Gaussian would give). `velocity_variance_m2s2`/`confidence` are directionally useful (they do
  correlate with error) but should not be treated as a precisely-calibrated Gaussian interval. See
  `docs/experiments.md` (Milestone 3 calibration section) and `docs/member1_output_contract.md`.
- **No input-noise-robust training.** Sensor noise and vibration are the largest perturbations tested in the M3
  robustness battery; the model was not trained with noise augmentation to counter them.
- **LOVO (retrained-per-fold) is not implemented**, per above.
- **No genuine 100 Hz data.** The production 100 Hz Member 2 interface (`src/inference/member2_interface.py`)
  decimates Member 2's real 100 Hz stream to this model's native 10 Hz resolution; it has not been validated against
  real 100 Hz recordings, because none exist in this repo. See `docs/production_100hz.md`.

## Documentation

- [`docs/data_protocol.md`](docs/data_protocol.md): dataset structure, allowed and forbidden inputs, target, windowing, splits, augmentation
- [`docs/architecture.md`](docs/architecture.md): modules, tensor contract, baseline/model/uncertainty methods, ONNX export and edge benchmark
- [`docs/experiments.md`](docs/experiments.md): results for every milestone and how to reproduce them
- [`docs/member1_output_contract.md`](docs/member1_output_contract.md): the `velocity_mps`/`velocity_variance_m2s2`/`confidence`/`timestamp` schema for Member 3, and the ONNX graph that also produces it
- [`docs/production_100hz.md`](docs/production_100hz.md): the production Member 2 100 Hz interface, why it decimates instead of retraining on fabricated data, and what is/isn't validated
