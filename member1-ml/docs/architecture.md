# Architecture

Member 1 estimates vehicle speed from 6-axis smartphone IMU data only. Member 3's EKF/UKF consumes the output.
This document covers the complete pipeline through **Milestone 4: inference, ONNX export, edge benchmark and
final audit** -- causal CNN/TCN point estimators (M2), the heteroscedastic uncertainty head and
augmentation-policy selection (M3), and the ONNX export / CPU benchmark (M4). See `docs/experiments.md` for
results and `docs/member1_output_contract.md` for the output schema.

## Data flow

```
member1_imu_speed.npz ──load_npz──► ImuDataset(imu (N,6), target (N,), session_id, trip_id, sample_idx, t_session_s)
        │                             ▲ only acc+gyr pass build_model_input / check_input_keys
        ▼
make_split (per trip_id, leakage assertions) ──► ds.subset(mask) for train / val / test
        ▼
window_end_indices(ds, T, stride)  ──►  ends (M,) int64      [causal, single-session, contiguous, finite]
        ▼
gather_windows / iter_window_chunks ──► float32 [B, T, 6]     (augmentation on train only; representation transform train+eval)
        ▼
baselines / VelocityNet  ──►  speed predictions (B,) m/s  ──►  metrics (overall / per trip & session / stationary-moving / speed bins)
        ▼ (VelocityNet only, deployment path)
predict_contract / ONNX export  ──►  {velocity_mps, uncertainty, confidence, timestamp}  ──►  Member 3's EKF/UKF
```

## Modules

| Module | Responsibility |
|---|---|
| `src/data/dataset.py` | Loads the NPZ read-only. Applies the allowed-input list and forbidden-key guard. Defines `ImuDataset`. |
| `src/data/inspect_dataset.py` | Dataset summary and validation: dimensions, target, finiteness, groups, sampling rate, continuity. CLI. |
| `src/data/windowing.py` | Builds causal, session-safe window indices and turns them into tensors. |
| `src/data/splits.py` | Fixed train/val/test split by trip, leakage assertions, LOVO folds. |
| `src/data/augmentation.py` | SO(3) rotation of `[B, T, 6]` windows, with one shared rotation for acc and gyr. |
| `src/models/baselines.py` | Constant-mean, ridge-on-window-statistics and physics-integration baselines. |
| `src/data/pipeline.py` | Shared experiment setup: config loading, load → validate → split, per-split window indices, JSON/CSV writers. |
| `src/models/tcn_velocity.py` | Causal `VelocityNet` (`cnn` / `tcn`) with built-in normalization buffers. |
| `src/training/losses.py` | Point-regression losses (Huber, MSE, L1) on m/s. |
| `src/training/train.py` | Seeding and determinism, device and AMP selection, the training loop (AdamW, warmup + cosine LR, early stopping), prediction, checkpoints. |
| `src/evaluation/metrics.py` | MAE and RMSE (m/s and km/h), R², and the breakdowns. |
| `src/evaluation/evaluate.py` | Full metric report for predictions at window end points, shared by all models. |
| `src/evaluation/plots.py` | PNG plots: baselines, training curves, model comparison, breakdowns, time series. |
| `scripts/run_baselines.py` | Milestone 1 experiment. |
| `scripts/run_training.py` | Milestone 2 experiment: trains every arch × window combination, evaluates it, and compares with the baselines. |
| `scripts/run_uncertainty.py` | Milestone 3 experiment: augmentation-policy comparison, final-selection matrix, point-vs-NLL ablation, single final test evaluation. |
| `src/inference/predict.py` | `predict_contract`: turns a checkpoint's predictions into the Member 1 output-contract records (see `docs/member1_output_contract.md`). |
| `src/inference/export_onnx.py` | Milestone 4: `InferenceModule` (wraps `forward_full` in the output-contract math), `export_model`, and ONNX Runtime verification helpers (`compare_pytorch_onnx`, `verify_shapes_and_finite`). |
| `src/inference/benchmark.py` | Milestone 4: CPU latency (PyTorch and ONNX Runtime), throughput, model size, parameter count. |
| `scripts/export_onnx.py` | Milestone 4 CLI: exports the final checkpoint, runs every verification check, writes the benchmark report. |
| `scripts/run_evaluation.py` | Milestone 4 CLI: evaluates an already-trained checkpoint (default: the M3 final one) on val/test/unseen-group splits, without retraining. |
| `scripts/run_ablation.py` | Milestone 4 CLI: consolidates the M2/M3 ablations already on disk into one table; does not retrain. |

## Tensor contract (shared with the future CNN/TCN)

- Window input: `float32 [B, T, 6]`, with `T ∈ {20, 40}` and channels `[acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z]`.
- Label: `float` speed at the last time step of the window, in m/s.

## Baselines

These are reference points, not candidate solutions. Every prediction is clipped to ≥ 0.

**A. Constant mean.** Always predicts the mean speed over training windows.

**B. Ridge on window statistics.** The window is expanded into 8 signals: acc x/y/z, gyr x/y/z, |acc| and |gyr|.
For each signal we compute mean, std, min, max, RMS and mean |first difference|, giving 48 features. These go through
`StandardScaler` (fit on train only) and then ridge regression. Alpha is picked by validation MAE. A second variant
trains the same model on SO(3)-rotated training windows.

**C. Physics integration.** A causal dead-reckoning pipeline that carries state through each session:
1. Estimate gravity with an exponential moving average (EMA) of acc.
2. Take the horizontal linear acceleration.
3. Estimate the forward axis as the principal eigenvector of an EMA covariance, keeping its sign continuous over time.
4. Integrate with a leak and zero-velocity updates (ZUPT). ZUPT fires when the rolling std of both |acc| and |gyr| is low.
5. Output speed as |v|.

The ZUPT acc threshold and leak time constant are picked by training MAE. The model's state resets at session starts and continuity
breaks. Its output at a row depends only on that row and earlier ones, which a test checks. It uses information from before the window,
so the window length only sets which rows are scored.

## Neural models (Milestone 2)

`VelocityNet`, in `src/models/tcn_velocity.py`, takes `[B, T, 6]` and returns `[B]` speed in m/s.

```
x [B,T,6] ─÷ input_scale─► transpose [B,6,T] ─► ResidualBlock × n ─► h [B,C,T]
    cnn: mean over T ─┐
    tcn: h[:, :, -1] ─┴─► Linear(C,1) ─► target_mean + target_std · out ─► speed [B]
ResidualBlock: CausalConv(k,d) → BN → ReLU → Dropout → CausalConv(k,d) → BN, (+ skip [1×1 conv+BN if C changes]) → ReLU → Dropout
CausalConv: left pad (k−1)·d, no right pad
```

| | CNN | TCN |
|---|---|---|
| blocks | 3, dilation 1 | 4, dilations 1, 2, 4, 8 |
| channels / kernel | 32 / 5 | 32 / 3 |
| receptive field (samples) | 25 (GAP covers the whole window) | 61 (≥ 40) |
| readout | global average over the window | last time step |
| parameters | 27,233 | 22,881 |
| checkpoint size | about 124 KB | about 124 KB |

- **Causality.** In eval mode, the feature at step t depends only on inputs at steps ≤ t, which tests verify. Every sample in a window is at or before the prediction point, so both readouts are causal. A TCN's last-step output also matches the output of a streaming model with a longer history, within its receptive field.
- **Normalization inside the model.** Fitted on training rows only and saved in the checkpoint:
  - one input scale per sensor (the acc RMS and the gyr RMS), with no per-axis mean, so it stays consistent under rotation
  - target mean and std applied to the output
- **Why BatchNorm.** In eval mode it's a per-step affine map, so causality holds exactly and it can fuse into the convolutions at export. GroupNorm or LayerNorm over time would mix time steps.
- **Clipping.** The model returns unclipped speed. `predict_windows` and `predict_indexed` clip it to ≥ 0 for evaluation, the same as the baselines.
- **Checkpoint format.** `torch.save` of `{arch, model_cfg, state_dict, epoch, val_metrics, seed}`. `load_checkpoint` rebuilds the model with `weights_only=True`.

## Uncertainty (Milestone 3)

Set `models.<arch>.uncertainty: true` (or pass `--uncertainty` to `scripts/run_training.py`) to add a
second linear head, `log_var_head`, reading the same pooled features as the mean head:

```
pooled ──head (mean)────────────────────────────► mean_mps = target_mean + target_std · head(pooled)
pooled ──log_var_head──► raw_log_var ──clamp[log_var_min, log_var_max]──► + 2·log(target_std) ──► log_var_mps2
```

- **Numerically stable by construction.** `raw_log_var` is clamped to a bounded range *before* any
  `exp()` is taken (in the loss, and in `log_var_to_sigma`), so the predictive variance
  (`exp(log_var_mps2)`) can never overflow to `inf` or underflow to `0`, however extreme the input or
  however the head's weights are set. `tests/test_training.py::test_uncertainty_head_clamp_bounds_arbitrary_head_weights`
  drives the head with deliberately extreme weights (not just extreme input) to prove this, because a
  freshly-initialised head's zero weights would otherwise mask a missing clamp.
- **Sane starting point.** `log_var_head`'s weight and bias are zero-initialised, so a freshly built
  model predicts `raw_log_var == 0`, i.e. `log_var_mps2 == 2·log(target_std)` — the dataset's marginal
  variance — before any input-dependent uncertainty signal is learned.
- **Loss.** `src/training/losses.py::heteroscedastic_gaussian_nll` — the standard heteroscedastic
  Gaussian negative log-likelihood, `0.5·(log_var + (y-mean)²·exp(-log_var) + log(2π))`, mean over the
  batch. Selected via `training.loss: nll` in the config (see `docs/experiments.md` for why point loss
  vs NLL was compared as an ablation, not assumed).
- **Warmup.** `training.nll_warmup_epochs` epochs first train the mean head alone with
  `training.warmup_loss` (a point loss); the variance head only starts receiving gradient once warmup
  ends. This is a standard stabiliser for heteroscedastic training (an untrained mean estimate,
  optimised jointly with an untrained variance estimate, can drive both to a bad local optimum early on).
- **Model selection stays MAE-based.** Early stopping and best-checkpoint selection always use
  validation MAE (from the mean head alone), for both point and uncertainty models — they are directly
  comparable on the same criterion. Validation NLL is logged every epoch for diagnostics only.
- **Calibration.** `src/evaluation/metrics.py`'s `calibration_report` (NLL, sharpness, error/sigma
  correlation, and a reliability curve of expected vs observed coverage per confidence level) and
  `src/evaluation/evaluate.py::evaluate_split_uncertainty` (the same per-trip/session/speed-bin/
  stationary-vs-moving breakdown as `evaluate_split`, plus that calibration report).
- **Confidence.** `VelocityNet.confidence_from_sigma` maps sigma to a bounded `(0, 1]` confidence
  using a reference scale, `confidence_ref_sigma`, fit from the model's own training-data sigma
  (median) after training and stored as a checkpoint buffer — no separate config value is needed at
  inference. See `docs/member1_output_contract.md`.

## Augmentation and representation policies (Milestone 3)

`src/data/augmentation.py` implements four combinations of a *representation* (a deterministic,
always-applied transform) and an *augmentation* (a random, training-only transform), selected by
`training.augmentation_policy`:

| Policy | Representation (train + eval) | Augmentation (train only) |
|---|---|---|
| `none` | identity | none |
| `so3` | identity | random full-SO(3) rotation (Milestone 2 default) |
| `yaw` | identity | random rotation about the vertical axis only |
| `gravity_yaw` | rotate the window's estimated gravity direction to `+z` | random rotation about the (now-canonical) vertical axis |

`build_augmentation(policy, ...)` returns the training-time function (or `None`); `representation_transform(policy)`
returns the deterministic function, which must be applied identically to validation, test and
inference windows whenever it is not the identity (i.e. for `gravity_yaw`). `scripts/run_training.py`
and `scripts/run_uncertainty.py` apply both consistently — see `docs/experiments.md` for the actual
comparison and the chosen policy.

## Robustness (Milestone 3)

`src/evaluation/robustness.py` perturbs already-windowed IMU tensors at evaluation time only
(`configs/member1.yaml`'s `robustness` section holds the magnitudes, documented there as engineering
assumptions, not measurements): additive sensor noise, heavier "vibration" noise, a constant
per-window sensor bias, a linear-ramp drift within the window, and a small-angle orientation
perturbation. `evaluate_perturbations` runs a model on the clean windows and every perturbation and
reports both the regression metrics and the calibration report for each, reusing
`src/evaluation/metrics.py` throughout rather than a separate metric implementation.

## Milestone 3 experiment orchestration

`scripts/run_uncertainty.py` reuses `scripts/run_training.py::run_one` for every individual training
run (no duplicated train/evaluate logic) across four phases -- augmentation-policy comparison, a
final-selection matrix (architecture × window, with the chosen policy and NLL loss), a point-vs-NLL
ablation of the winning config, and a single final test-set evaluation of the already-trained winning
checkpoint. `run_one` takes an `evaluate_test` flag so every exploratory phase can run without ever
computing a metric from the S-series test set; only phase 4 sets it, and only for the model already
chosen by validation. See `docs/experiments.md` for what actually happened when this ran.

## Inference contract (`src/inference/predict.py`)

`predict_contract(model, imu, ends, window, timestamps, device, transform=None)` is the single place
that turns a loaded checkpoint's predictions into output-contract records
(`docs/member1_output_contract.md`). It calls `predict_indexed`/`predict_indexed_uncertainty` from
`src.training.train` (the same prediction path used everywhere else in this repo -- no separate
inference-only implementation of normalization or the forward pass exists), clips `velocity_mps` to
`>= 0`, computes `confidence` from the checkpoint's own `confidence_ref_sigma` buffer, and passes
`timestamp` through unchanged from the caller. `transform`, if the checkpoint's augmentation policy is
`gravity_yaw`, must be `src.data.augmentation.representation_transform("gravity_yaw")` -- every other
policy's transform is the identity, so passing nothing is safe for the shipped (`yaw`) final model.

## ONNX export and edge benchmark (Milestone 4)

`src/inference/export_onnx.py::InferenceModule` wraps a trained `VelocityNet` so its forward pass
returns exactly the numeric output-contract fields (`velocity_mps`, and for an uncertainty model also
`uncertainty` and `confidence`) -- the same clamp/exp/confidence-from-sigma math `predict_contract`
uses, not a reimplementation. `export_model(model, window, path)` traces this wrapper with
`torch.onnx.export(..., dynamo=False, opset_version=17)`: the legacy TorchScript-based exporter, kept
deliberately instead of the newer `torch.export`-based default (a `DeprecationWarning` on recent torch
versions), because that one needs an extra `onnxscript` dependency this project doesn't otherwise
require, and the legacy exporter already verifies correctly (see `docs/experiments.md`'s Milestone 4
section for the actual PyTorch-vs-ONNX agreement numbers). Only the batch axis is dynamic; window
length is fixed at export time, matching every other place in this repo that treats window length as
a fixed config value.

`verify_shapes_and_finite` and `compare_pytorch_onnx` (also in `export_onnx.py`) are the two
verification primitives `scripts/export_onnx.py` and `tests/test_inference.py` both build on: the
first checks dynamic-batch support, output shapes and finiteness independent of PyTorch; the second
runs the same input through both PyTorch and ONNX Runtime and reports per-output max/mean absolute
difference and an `allclose` verdict at a caller-supplied tolerance.

`src/inference/benchmark.py` measures CPU latency (`pytorch_cpu_latency_ms`, `onnx_cpu_latency_ms`),
throughput, ONNX file size and parameter count. Both functions accept an explicit thread-count
override, because for a model this small (27k parameters), multi-threaded dispatch overhead can
dominate actual compute time at batch size 1 -- `scripts/export_onnx.py` reports both a
"default-threading" and a "single-threaded" number for this reason (see `docs/experiments.md`).
`process_memory_mb` reports `None` when `psutil` isn't installed rather than adding it as a new
project dependency for one optional number.

`scripts/export_onnx.py` is the CLI: it resolves the final checkpoint from
`results/uncertainty/final_model.json` by default, exports it, runs every verification check listed
above (raising if any fails), runs the CPU benchmark, and writes the combined report to
`<checkpoint-name>.onnx_report.json` next to the `.onnx` file. Both the `.onnx` file and its report
are untracked (`*.onnx` is in `.gitignore`, matching the existing checkpoint-artifact policy), so
`docs/experiments.md`'s Milestone 4 section is the durable record of what was measured.
