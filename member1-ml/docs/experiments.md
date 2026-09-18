# Experiments

## Milestone 1: baselines

Command: `python scripts/run_baselines.py` (config `configs/member1.yaml`, seed 42). Outputs go to `results/baselines/`:
`summary.csv`, `results.json` (full breakdowns, chosen hyperparameters, split membership, window counts), and PNG plots.

The tables below are generated from `results/baselines/results.json` for the run on this dataset. Rerunning the command reproduces them.

### Protocol

- Train on Vw* + Vfa02 windows (stride 5). Evaluate on M (validation) and S* (test) windows (stride 1). See `docs/data_protocol.md`.
- Every model sees only `[B, T, 6]` IMU windows. The physics baseline is the exception: it sees the causal IMU stream of its own session.
- Hyperparameter selection:
  - Ridge alpha: chosen by **validation** MAE.
  - Physics ZUPT threshold and leak: chosen by **training** MAE.
  - Constant mean: fit on training targets.
- Test data is never used for fitting or selection.

### Window counts

| window (samples) | train (stride 5) | val (stride 1) | test (stride 1) |
|---|---|---|---|
| 20 | 61055 | 105676 | 301580 |
| 40 | 60987 | 105636 | 301400 |

### Overall metrics

| window | model | split | n windows | MAE (m/s) | RMSE (m/s) | R² | MAE (km/h) |
|---|---|---|---|---|---|---|---|
| 20 (2 s) | constant_mean | train | 61055 | 7.679 | 9.053 | 0.000 | 27.65 |
| 20 (2 s) | constant_mean | val | 105676 | 9.017 | 10.382 | -2.354 | 32.46 |
| 20 (2 s) | constant_mean | test | 301580 | 10.391 | 11.587 | -2.183 | 37.41 |
| 20 (2 s) | ridge_features | train | 61055 | 5.915 | 7.059 | 0.392 | 21.29 |
| 20 (2 s) | ridge_features | val | 105676 | 5.177 | 6.412 | -0.279 | 18.64 |
| 20 (2 s) | ridge_features | test | 301580 | 5.595 | 6.853 | -0.113 | 20.14 |
| 20 (2 s) | ridge_features_so3aug | train | 61055 | 6.100 | 7.241 | 0.360 | 21.96 |
| 20 (2 s) | ridge_features_so3aug | val | 105676 | 6.107 | 7.121 | -0.578 | 21.98 |
| 20 (2 s) | ridge_features_so3aug | test | 301580 | 6.608 | 7.624 | -0.378 | 23.79 |
| 20 (2 s) | physics_integration | train | 61055 | 14.115 | 16.416 | -2.288 | 50.81 |
| 20 (2 s) | physics_integration | val | 105676 | 7.371 | 9.331 | -1.710 | 26.53 |
| 20 (2 s) | physics_integration | test | 301580 | 6.693 | 8.999 | -0.920 | 24.10 |
| 40 (4 s) | constant_mean | train | 60987 | 7.676 | 9.051 | 0.000 | 27.63 |
| 40 (4 s) | constant_mean | val | 105636 | 9.019 | 10.385 | -2.357 | 32.47 |
| 40 (4 s) | constant_mean | test | 301400 | 10.394 | 11.590 | -2.184 | 37.42 |
| 40 (4 s) | ridge_features | train | 60987 | 5.554 | 6.691 | 0.454 | 19.99 |
| 40 (4 s) | ridge_features | val | 105636 | 4.860 | 6.111 | -0.162 | 17.50 |
| 40 (4 s) | ridge_features | test | 301400 | 5.053 | 6.383 | 0.034 | 18.19 |
| 40 (4 s) | ridge_features_so3aug | train | 60987 | 5.818 | 6.995 | 0.403 | 20.95 |
| 40 (4 s) | ridge_features_so3aug | val | 105636 | 5.488 | 6.571 | -0.344 | 19.76 |
| 40 (4 s) | ridge_features_so3aug | test | 301400 | 6.333 | 7.448 | -0.315 | 22.80 |
| 40 (4 s) | physics_integration | train | 60987 | 14.117 | 16.417 | -2.290 | 50.82 |
| 40 (4 s) | physics_integration | val | 105636 | 7.373 | 9.333 | -1.711 | 26.54 |
| 40 (4 s) | physics_integration | test | 301400 | 6.695 | 9.001 | -0.921 | 24.10 |

Selected hyperparameters:
- window 20: ridge alpha = 1000, ridge+SO(3) alpha = 1, physics zupt_acc_std = 0.05, leak_tau_s = inf
- window 40: ridge alpha = 1000, ridge+SO(3) alpha = 100, physics zupt_acc_std = 0.05, leak_tau_s = inf

### Window = 40: stationary (true speed < 0.5 m/s) vs moving

| model | split | stationary MAE (n) | moving MAE (n) |
|---|---|---|---|
| constant_mean | val | 18.59 (11094) | 7.90 (94542) |
| constant_mean | test | 18.58 (37196) | 9.24 (264204) |
| ridge_features | val | 10.53 (11094) | 4.19 (94542) |
| ridge_features | test | 10.62 (37196) | 4.27 (264204) |
| ridge_features_so3aug | val | 11.42 (11094) | 4.79 (94542) |
| ridge_features_so3aug | test | 11.46 (37196) | 5.61 (264204) |
| physics_integration | val | 2.91 (11094) | 7.90 (94542) |
| physics_integration | test | 0.64 (37196) | 7.55 (264204) |

### Window = 40: test MAE (m/s) per trip

| model | S1 | S2 | S3a | S3b | S3c | S4 |
|---|---|---|---|---|---|---|
| constant_mean | 11.30 | 11.05 | 8.74 | 13.06 | 9.39 | 9.84 |
| ridge_features | 4.22 | 5.33 | 4.26 | 6.20 | 5.70 | 5.11 |
| ridge_features_so3aug | 6.13 | 7.06 | 5.00 | 8.41 | 6.27 | 5.91 |
| physics_integration | 5.29 | 5.75 | 6.97 | 3.68 | 9.15 | 7.64 |

Per-session, per-speed-bin and window = 20 breakdowns are in `results.json`.
Plots: `mae_overview.png`, `test_mae_by_speed_bin_w{20,40}.png`, `test_timeseries_w{20,40}.png`.

### Observations (from the numbers above)

- **Ridge on window statistics** is the strongest baseline on both validation and test. It still has negative or near-zero R², so it explains little of the speed variance outside training. In the per-speed-bin breakdown, its errors are lowest around 10–15 m/s and grow at standstill and at high speed. Its predictions regress towards mid-range speeds.
- **The 4 s window beats the 2 s window** for ridge on validation and test.
- **SO(3) augmentation makes ridge worse** on both splits. The per-axis statistics exploit the consistent phone orientation in these recordings. A rotation-invariant linear model gives up that shortcut and has too little capacity to replace it. This result doesn't tell us whether augmentation will help a CNN/TCN; that is an ablation for Milestone 2.
- **Physics integration** does very well while stationary, thanks to ZUPT. While moving, it is no better than the constant mean. Leaky integration forgets cruise speed, and unleaky integration drifts (the grid picked no leak). It is a lower bound for naive dead reckoning.
- **Constant mean** marks the no-information level: MAE of 9.0 m/s on validation and 10.4 m/s on test. The training trips are faster on average than the M and S trips, which is why its R² is strongly negative.


## Milestone 2: causal CNN / TCN

Command (main benchmark): `python scripts/run_training.py`. Ablation: `python scripts/run_training.py --no-so3 --tag m2abl_noso3 --results-dir results/neural_ablation_no_so3`.
Environment: NVIDIA GeForce RTX 4050 Laptop GPU, torch 2.11.0+cu128, bf16 autocast, deterministic kernels, seed 42.
Outputs:
- `experiments/<tag>_<arch>_w<window>/`: `best.pt`, `history.csv/json`, `metrics.json`, `training_curves.png`, `test_timeseries.png`
- `results/neural/` and `results/neural_ablation_no_so3/`: `summary.csv`, `results.json`, `best_model.json`, `comparison_with_baselines.csv`, and comparison plots

The tables below are generated from those JSON files.

### Protocol

- Same split, windows, window counts and evaluation code as the baselines. The runner asserts the window counts match exactly.
- Input normalization is one scale per sensor (the RMS of the acc axes and the RMS of the gyr axes). Target mean and std are fitted on **training** rows and labels only, and stored in the checkpoint.
- Training settings:
  - AdamW with lr 0.002 and weight decay 0.01
  - batch size 256
  - 2 warmup epochs, then cosine decay to 0.02×lr at 60 epochs
  - Huber loss (δ = 1.0 m/s), gradient clipping at 1.0
- Validation MAE is computed every epoch. Early stopping uses patience 10 (min delta 0.005 m/s), and the best-val-MAE checkpoint is kept. The test split is evaluated once per run, with that checkpoint reloaded from disk.
- The main benchmark uses SO(3) rotation augmentation (the project specification), re-drawn each epoch. Model and training hyperparameters were fixed before the runs and **not tuned** on validation or test data.
- Best model selection across runs uses validation MAE.

### Results

| augmentation | model | window | params | best/run epochs | train time (s) | train MAE | val MAE | val RMSE | val R² | test MAE (m/s) | test RMSE | test R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SO(3) (main) | cnn | 20 (2 s) | 27,233 | 22/32 | 117 | 3.378 | 6.689 | 8.499 | -1.248 | 6.898 (24.8 km/h) | 9.191 | -1.003 |
| SO(3) (main) | tcn | 20 (2 s) | 22,881 | 25/35 | 145 | 3.487 | 6.902 | 8.630 | -1.318 | 7.546 (27.2 km/h) | 9.775 | -1.265 |
| SO(3) (main) | cnn | 40 (4 s) | 27,233 | 5/15 | 62 | 3.692 | 5.739 | 7.324 | -0.670 | 6.991 (25.2 km/h) | 8.974 | -0.909 |
| SO(3) (main) | tcn | 40 (4 s) | 22,881 | 7/17 | 76 | 3.581 | 6.376 | 8.005 | -0.995 | 6.468 (23.3 km/h) | 8.571 | -0.741 |
| none (ablation) | cnn | 20 (2 s) | 27,233 | 24/34 | 103 | 2.154 | 4.692 | 6.282 | -0.228 | 5.295 (19.1 km/h) | 7.422 | -0.306 |
| none (ablation) | tcn | 20 (2 s) | 22,881 | 15/25 | 90 | 2.553 | 5.389 | 7.045 | -0.544 | 5.566 (20.0 km/h) | 7.737 | -0.419 |
| none (ablation) | cnn | 40 (4 s) | 27,233 | 4/14 | 43 | 2.415 | 4.469 | 5.957 | -0.105 | 5.587 (20.1 km/h) | 7.615 | -0.375 |
| none (ablation) | tcn | 40 (4 s) | 22,881 | 9/19 | 72 | 2.374 | 4.370 | 5.788 | -0.043 | 4.727 (17.0 km/h) | 6.702 | -0.065 |

Best main-benchmark model, selected by validation MAE: **cnn_w40**, val MAE 5.739 m/s, test MAE 6.991 m/s, checkpoint `experiments/m2_cnn_w40/best.pt`.
The best model without augmentation (ablation) is tcn_w40: val MAE 4.370 m/s, test MAE 4.727 m/s, checkpoint `experiments/m2abl_noso3_tcn_w40/best.pt`.

Baselines on the same windows (from Milestone 1):

| model | window | val MAE | val RMSE | val R² | test MAE | test RMSE | test R² |
|---|---|---|---|---|---|---|---|
| constant_mean | 20 | 9.017 | 10.382 | -2.354 | 10.391 | 11.587 | -2.183 |
| ridge_features | 20 | 5.177 | 6.412 | -0.279 | 5.595 | 6.853 | -0.113 |
| ridge_features_so3aug | 20 | 6.107 | 7.121 | -0.578 | 6.608 | 7.624 | -0.378 |
| physics_integration | 20 | 7.371 | 9.331 | -1.710 | 6.693 | 8.999 | -0.920 |
| constant_mean | 40 | 9.019 | 10.385 | -2.357 | 10.394 | 11.590 | -2.184 |
| ridge_features | 40 | 4.860 | 6.111 | -0.162 | 5.053 | 6.383 | 0.034 |
| ridge_features_so3aug | 40 | 5.488 | 6.571 | -0.344 | 6.333 | 7.448 | -0.315 |
| physics_integration | 40 | 7.373 | 9.333 | -1.711 | 6.695 | 9.001 | -0.921 |

### Window = 40: stationary vs moving

| model | split | stationary MAE | moving MAE |
|---|---|---|---|
| ridge_features | val | 10.53 | 4.19 |
| ridge_features | test | 10.62 | 4.27 |
| ridge_features_so3aug | val | 11.42 | 4.79 |
| ridge_features_so3aug | test | 11.46 | 5.61 |
| SO(3) cnn | val | 0.71 | 6.33 |
| SO(3) cnn | test | 1.08 | 7.82 |
| SO(3) tcn | val | 1.81 | 6.91 |
| SO(3) tcn | test | 1.87 | 7.11 |
| no-aug cnn | val | 0.43 | 4.94 |
| no-aug cnn | test | 0.80 | 6.26 |
| no-aug tcn | val | 1.48 | 4.71 |
| no-aug tcn | test | 1.57 | 5.17 |

### Window = 40: test MAE (m/s) per speed bin

| model (w40, test) | [0,0.5) | [0.5,5) | [5,10) | [10,15) | [15,20) | [20,25) | [25,30) | [30,inf) |
|---|---|---|---|---|---|---|---|---|
| ridge_features | 10.6 | 6.5 | 3.6 | 1.9 | 4.6 | 9.6 | 13.4 | 16.7 |
| physics_integration | 0.6 | 2.1 | 4.7 | 8.9 | 13.5 | 19.8 | 24.6 | 28.0 |
| SO(3) cnn | 1.1 | 6.6 | 8.9 | 6.8 | 6.3 | 6.3 | 14.4 | 30.2 |
| SO(3) tcn | 1.9 | 3.7 | 7.3 | 7.2 | 8.2 | 7.6 | 15.0 | 29.1 |
| no-aug cnn | 0.8 | 3.7 | 6.3 | 6.7 | 6.5 | 5.5 | 11.5 | 28.2 |
| no-aug tcn | 1.6 | 2.5 | 4.6 | 5.4 | 6.7 | 7.0 | 13.2 | 28.6 |

### Window = 40: test MAE (m/s) per trip

| model (w40, test) | S1 | S2 | S3a | S3b | S3c | S4 |
|---|---|---|---|---|---|---|
| ridge_features | 4.22 | 5.33 | 4.26 | 6.20 | 5.70 | 5.11 |
| physics_integration | 5.29 | 5.75 | 6.97 | 3.68 | 9.15 | 7.64 |
| SO(3) cnn | 8.52 | 7.56 | 6.11 | 6.09 | 9.63 | 4.69 |
| SO(3) tcn | 6.28 | 6.83 | 8.03 | 4.68 | 9.79 | 4.48 |
| no-aug cnn | 5.34 | 5.95 | 4.93 | 4.39 | 8.59 | 4.35 |
| no-aug tcn | 3.60 | 4.61 | 5.35 | 3.49 | 8.72 | 3.75 |

### Diagnosis and findings

- **With SO(3) augmentation, which the spec requires, neither neural model beats ridge.** The best, CNN at 4 s, reaches val 5.74 and test 6.99 m/s; ridge reaches val 4.86 and test 5.05 m/s. This is not a pipeline bug:
  - The networks fit the training windows far better than ridge.
  - Their bias on training windows is near zero.
  - Reloaded checkpoints reproduce the val MAE recorded during training.
  - Rerunning gives bit-identical metrics.
- **Full SO(3) augmentation is the main cause.** In every session, including val and test, the mean accelerometer vector points along +z (normalized ≈ [0, 0, 1]). All recordings share one phone orientation. Random rotations remove a cue that this benchmark rewards, and ridge also gets worse with augmentation (4.86 → 5.49 val at 4 s). With augmentation off and nothing else changed, **TCN at 4 s reaches val 4.37 / test 4.73 m/s, beating ridge**, and CNN at 4 s reaches val 4.47 / test 5.59.
- **The networks and ridge fail in different places.** At standstill, all network variants have val MAE between 0.43 and 1.81 m/s, against ridge's 10.53 m/s. While moving, every network variant is worse than ridge. Even the no-augmentation TCN at 4 s reaches 4.71 val and 5.17 test, against ridge's 4.19 and 4.27, so its overall win comes from standstill. The networks' errors grow at the highest speeds.
- **Input domain shift across vehicles.** Mean |gyr| is 0.27 rad/s on training rows and 0.11 rad/s on validation rows. Validation MAE swings from epoch to epoch (see `training_curves.png`), and early stopping picks early epochs.
- **Open decision, not taken here:** the augmentation policy for the deployed model. Options are keeping full SO(3), dropping it, or adding gravity alignment and augmenting only yaw. The no-augmentation result was chosen after looking at validation, and its test numbers have now been seen, so treat it as an ablation, not a tuned benchmark.


## Milestone 3: uncertainty, augmentation-policy selection, robustness, final model

Command: `python scripts/run_uncertainty.py` (requires `results/baselines/results.json`,
`results/neural/results.json` and `results/neural_ablation_no_so3/results.json` to already exist --
run `run_baselines.py`, `run_training.py`, and `run_training.py --no-so3 --tag m2abl_noso3
--results-dir results/neural_ablation_no_so3` first). Reuses `scripts/run_training.py::run_one` for
every individual training run. Outputs: `results/uncertainty/` (`results.json`, `final_model.json`,
`selection_summary.csv`, plots) and `experiments/m3_*/` (one directory per run, each with its own
checkpoint, history and training curve).

**The test set (S-series) is touched exactly once**, at the very end (phase 4), by the model already
chosen using validation evidence alone. Every phase before that passes `evaluate_test=False` and
never computes a metric against test data.

### Phase 1: augmentation-policy comparison (validation only)

TCN, 4 s window, point (Huber) loss -- the Milestone 2 configuration, so the "so3" and "none" rows
are the *existing* Milestone 2 / ablation runs (re-used, not retrained: nothing about that config
changed). "yaw" and "gravity_yaw" are new runs, evaluated on validation only.

| policy | source | val MAE | val RMSE | val R² |
|---|---|---|---|---|
| so3 | reused (M2) | 6.376 | 8.005 | -0.995 |
| none | reused (M2) | 4.370 | 5.788 | -0.043 |
| yaw **(chosen)** | retrained here | 4.751 | 6.160 | -0.181 |
| gravity_yaw | retrained here | 5.063 | 6.544 | -0.333 |

**Chosen policy: `yaw`.** "none" has the best raw validation MAE, but every
recorded session in this dataset shares one fixed mounting tilt (see Milestone 2's finding in this
same file), so a model trained with *no* rotation invariance at all has no defence against a
differently-mounted phone in the field -- a realistic deployment scenario this single-orientation
benchmark cannot detect or penalise. Between the two yaw-aware, deployment-safer policies (heading is
genuinely arbitrary in a real vehicle; tilt is comparatively consistent for a given mount, so
targeting only yaw-invariance is a smaller, better-justified ask than full SO(3)), `yaw` clearly beat
`gravity_yaw` on validation (4.751 vs 5.063 m/s). This is a
real, measured result, not the expected direction: `gravity_yaw`'s per-window gravity estimate is a
noisy 4 s average that itself moves under vehicle acceleration, so on a dataset where the raw data is
*already* well aligned to gravity, that estimation adds noise for no compensating benefit, while
`yaw` keeps the (already-good) raw tilt untouched and only randomises heading.

### Phase 2: final-selection matrix (policy = `yaw`, heteroscedastic NLL loss, validation only)

Every combination of architecture and window, all built with `uncertainty=True` and trained with the
heteroscedastic Gaussian NLL loss (3 warmup epochs of Huber first -- see `docs/architecture.md`).

| candidate | val MAE | val RMSE | val R² | val NLL | params | CPU latency (ms) | worst robustness MAE |
|---|---|---|---|---|---|---|---|
| cnn_w20 | 4.364 | 5.992 | -0.117 | 3.437 | 27,266 | 2.932 | 8.391 |
| tcn_w20 | 4.610 | 6.049 | -0.139 | 3.808 | 22,914 | 1.453 | 7.812 |
| cnn_w40 **(selected)** | 4.124 | 5.548 | 0.042 | 3.478 | 27,266 | 2.884 | 7.789 |
| tcn_w40 | 4.399 | 5.807 | -0.050 | 3.819 | 22,914 | 1.245 | 7.369 |

"worst robustness MAE" is the highest MAE any of the five validation-set perturbations below produced
for that candidate (full breakdown):

| candidate | clean | sensor_noise | vibration | sensor_bias | sensor_drift | orientation |
|---|---|---|---|---|---|---|
| cnn_w20 | 4.364 | 6.238 | 8.391 | 5.343 | 4.449 | 4.237 |
| tcn_w20 | 4.610 | 5.752 | 7.812 | 5.127 | 4.570 | 4.553 |
| cnn_w40 | 4.124 | 6.439 | 7.789 | 4.951 | 4.618 | 4.105 |
| tcn_w40 | 4.399 | 5.523 | 7.369 | 4.666 | 4.376 | 4.598 |

**Selected: `cnn_w40`.** It has the best validation MAE and R², the best or near-best robustness
under every perturbation except sensor noise/vibration (where TCN@40 is somewhat better -- noted
under "Not yet run / known limitations" below), and its parameter count and CPU latency
(27,266 params, 2.88 ms/window on
this development machine's CPU, plain PyTorch, no ONNX) are well within the "lightweight" budget this
project targets -- comparable to every other candidate in this matrix, so latency was not a
deciding factor here.

### Phase 3: point loss vs heteroscedastic NLL loss (ablation, validation only)

The winning (arch, window, policy) config retrained with a point (Huber) loss instead of NLL, to
isolate what adding the uncertainty head costs in point accuracy.

| loss | val MAE | val RMSE | val R² |
|---|---|---|---|
| nll (heteroscedastic, final model) | 4.124 | 5.548 | 0.042 |
| huber (point, ablation) | 4.152 | 5.576 | 0.032 |

Adding the uncertainty head and switching to the heteroscedastic NLL loss did **not** cost point
accuracy here -- the NLL-trained model's validation MAE is marginally *better* than its point-loss
counterpart (a small, likely noise-level difference, not a claim that NLL training reliably beats
point training). Uncertainty modelling was not a measurable point-accuracy tax on this data.

### Phase 4: final model, evaluated ONCE on the untouched S-series test set

**Final model: `cnn_w40`** (CNN, 40 samples = 4 s,
`yaw` augmentation policy, heteroscedastic uncertainty head).
Checkpoint: `experiments/m3_final_cnn_w40/final.pt` (confidence reference `confidence_ref_sigma_mps` =
3.629, fit from **training** sigma only, per
`docs/member1_output_contract.md`).

**Overall test metrics:** MAE = 4.786 m/s (17.23 km/h), RMSE = 6.662 m/s, R² = -0.052 (n = 301,400).

**Comparison with earlier milestones** (same test set, same windows):

| model | test MAE (m/s) | orientation-robust? |
|---|---|---|
| M1 ridge (4 s) | 5.053 | no |
| M2 best point model, no augmentation (TCN, 4 s) | 4.727 | no (fixed to this dataset's one orientation) |
| M2 best point model, full SO(3) augmentation (CNN, 4 s) | 6.991 | yes, but at a large accuracy cost |
| **M3 final (this milestone)** | **4.786** | yes (yaw-robust; not tilt-robust) |

The M3 final model costs about 0.059 m/s of test MAE
relative to Milestone 2's best (but non-orientation-robust, uncertainty-free) point model, in exchange
for heading robustness and a calibrated uncertainty output -- both required by the project
specification. It clearly beats the ridge baseline and the full-SO(3) CNN.

**Stationary vs moving:** stationary MAE = 1.384 m/s (n=37,196), moving MAE = 5.265 m/s (n=264,204).

**Per speed bin:**

| speed bin (m/s) | n | MAE | RMSE |
|---|---|---|---|
| [0,0.5) | 37,196 | 1.384 | 2.005 |
| [0.5,5) | 44,362 | 3.188 | 4.837 |
| [5,10) | 99,367 | 5.181 | 6.889 |
| [10,15) | 76,071 | 5.249 | 6.337 |
| [15,20) | 25,886 | 5.671 | 6.906 |
| [20,25) | 10,951 | 5.887 | 7.769 |
| [25,30) | 5,290 | 13.056 | 14.818 |
| [30,inf) | 2,277 | 24.263 | 24.460 |

**Per test trip:**

| trip | n | MAE | RMSE | R² |
|---|---|---|---|---|
| S1 | 51,704 | 4.998 | 6.688 | -1.198 |
| S2 | 93,632 | 5.014 | 6.675 | -0.292 |
| S3a | 24,514 | 4.679 | 6.034 | 0.005 |
| S3b | 6,681 | 4.307 | 5.985 | -3.051 |
| S3c | 37,138 | 6.870 | 9.818 | -0.413 |
| S4 | 87,731 | 3.603 | 4.987 | 0.486 |

### Uncertainty calibration (test set)

NLL = 4.722, mean sigma = 3.522 m/s, median sigma = 3.383 m/s,
error/sigma correlation = 0.235 (positive, as wanted: windows the model flags as more uncertain do tend to have larger errors).

| nominal level | z | expected coverage | observed coverage |
|---|---|---|---|
| 0.5 | 0.674 | 0.500 | 0.307 |
| 0.68 | 0.994 | 0.680 | 0.472 |
| 0.8 | 1.282 | 0.800 | 0.611 |
| 0.9 | 1.645 | 0.900 | 0.718 |
| 0.95 | 1.960 | 0.950 | 0.778 |
| 0.99 | 2.576 | 0.990 | 0.852 |

**The model is overconfident on the test set: observed coverage is below the nominal level at every
confidence band** (e.g. 47.2% of test points fall within the
predicted 1-sigma interval, against the 68% a well-calibrated Gaussian would give). Validation-set NLL
for this model was 3.478, notably
better than the test NLL above -- calibration learned on M does not fully transfer to the S-series
trips, which have a different speed/driving profile (see `docs/data_protocol.md`). `uncertainty`
should be read as directionally informative (it does correlate with error) rather than as a precise
Gaussian interval; recalibration (e.g. temperature scaling of sigma, fit on a held-out calibration
split) is flagged as future work rather than attempted here, since it would require carving out
another data split this project does not currently have.

### Robustness (test set, final model)

| perturbation | MAE | RMSE | R² | NLL | mean sigma |
|---|---|---|---|---|---|
| clean | 4.786 | 6.662 | -0.052 | 4.722 | 3.522 |
| sensor_noise | 6.954 | 8.478 | -0.704 | 4.078 | 5.113 |
| vibration | 8.833 | 10.407 | -1.567 | 4.552 | 5.289 |
| sensor_bias | 5.733 | 7.544 | -0.349 | 4.639 | 4.071 |
| sensor_drift | 5.402 | 7.024 | -0.169 | 4.542 | 3.838 |
| orientation | 4.698 | 6.347 | 0.045 | 4.105 | 3.741 |

### Unseen-group diagnostic (test set, final model)

**Diagnostic only -- not part of the benchmark.** Trips Vfa01, Vta1a, Vta1b, Y1 match no split rule (see `docs/data_protocol.md`)
and were never used for training, validation, hyperparameter selection or model selection. Evaluating the final model on them
(after it was already chosen) checks generalisation to genuinely unseen recording sessions, though they share the same
recording setup (and so the same fixed mounting orientation) as the rest of the dataset -- this is not a test of a
different vehicle's IMU characteristics or a different phone mounting.

- Overall: n=104,403, MAE=4.999 m/s, RMSE=6.396 m/s, R²=0.045
- Uncertainty: NLL=4.459, mean sigma=3.991 m/s

| trip | n | MAE |
|---|---|---|
| Vfa01 | 11,399 | 4.159 |
| Vta1a | 25,537 | 5.069 |
| Vta1b | 871 | 4.484 |
| Y1 | 66,596 | 5.123 |

Orientation perturbation (±15°, comparable to a mounting error, not a full remount) leaves test MAE
essentially unchanged, as expected for a model trained with yaw augmentation. Sensor noise and the
heavier "vibration" noise are by far the most damaging perturbations tested (both roughly double the
error) -- this model was not trained with any input-noise augmentation, so this is an honest gap, not
a claim of noise robustness; it is flagged under "Not yet run" below.

### Not yet run / known limitations

- **Noise-robust training.** No noise/vibration augmentation was used during training; the robustness
  numbers above show this is the model's weakest point. Adding input-noise augmentation (analogous to
  the orientation augmentation already used) is a natural next step, not attempted here to keep this
  milestone's training-time changes limited to what the spec asked for.
- **Sigma recalibration.** See the calibration paragraph above.
- **TCN's slightly better noise/vibration robustness was not decisive.** TCN@40's validation
  robustness under sensor noise and vibration is somewhat better than CNN@40's (see the phase 2
  robustness table), but CNN@40 wins on validation MAE, R², and every other perturbation, so it was
  selected; this trade-off is recorded here rather than hidden.
- **LOVO evaluation** (a *retrained-per-fold* leave-one-vehicle-out benchmark) remains unimplemented:
  `src/data/splits.py::lovo_folds` provides the fold machinery, but running it means training one
  model per held-out trip family, which is out of scope for a deployment/inference milestone. ONNX
  export and CPU-latency benchmarking, listed here previously as future work, are now done -- see
  Milestone 4 below.


## Milestone 4: inference, ONNX export, edge benchmark, final audit

Command: `python scripts/export_onnx.py` (exports and verifies; requires `results/uncertainty/final_model.json`,
i.e. Milestone 3 must already have run). Also: `python scripts/run_evaluation.py` (reproduces the M3 final
checkpoint's val/test/unseen-group numbers from disk, no retraining) and `python scripts/run_ablation.py`
(consolidates the M2/M3 ablations already run into one table -- no retraining). No model was trained or
selected in this milestone; the M3 final checkpoint (`experiments/m3_final_cnn_w40/final.pt`) is exported
and benchmarked as-is.

### ONNX export and verification

`src/inference/export_onnx.py::InferenceModule` wraps the checkpoint's `forward_full` in exactly the
`predict_contract` math (mean clamped to >= 0; sigma from the clamped log-variance; confidence from the
model's own `confidence_ref_sigma` buffer), so the exported graph outputs `velocity_mps`/`uncertainty`/`confidence`
directly (`timestamp` is never a model output, in ONNX or in `predict_contract` -- the caller's IMU stream
supplies it). Exported with `torch.onnx.export(..., dynamo=False)` (opset 17): the legacy TorchScript-based
exporter, not the newer `torch.export`-based one, because the latter needs the extra `onnxscript` dependency
this project doesn't otherwise need (`CLAUDE.md`'s "no unnecessary dependencies" rule) and the legacy exporter
already verifies correctly here. Only the batch dimension is dynamic; the window length (40 samples) is fixed
at export time, matching how this repo always treats window length as a fixed config value, never something
inferred at inference time.

Checks run by `scripts/export_onnx.py` against `experiments/m3_final_cnn_w40/final.onnx`, in order:

1. **Shape / dynamic batch / finiteness**: batch sizes 1, 8, 64 all produce correctly-shaped, all-finite outputs.
2. **Value ranges**: `velocity_mps >= 0`, `uncertainty > 0`, `0 < confidence <= 1`, on a synthetic random batch.
3. **PyTorch vs ONNX Runtime numerical agreement**, at `atol=1e-4, rtol=1e-3`:

   | input | output | max abs diff | mean abs diff | within tolerance |
   |---|---|---|---|---|
   | 512 real validation-split windows | `velocity_mps` | 1.91e-5 | 3.01e-6 | yes |
   | 512 real validation-split windows | `uncertainty` | 6.20e-6 | 9.59e-7 | yes |
   | 512 real validation-split windows | `confidence` | 3.28e-7 | 6.33e-8 | yes |
   | synthetic random batch (16, 40, 6) | `velocity_mps` | 5.72e-6 | 2.62e-6 | yes |
   | synthetic random batch (16, 40, 6) | `uncertainty` | 1.43e-6 | 4.17e-7 | yes |
   | synthetic random batch (16, 40, 6) | `confidence` | 8.94e-8 | 1.86e-8 | yes |

   The agreement check deliberately uses **validation**-split windows, not test: the S-series test set was
   already touched exactly once (Milestone 3, phase 4) and this export-verification step doesn't need it --
   it is checking that ONNX reproduces the already-trained PyTorch model, not evaluating accuracy.
4. **Plain CPU ONNX Runtime inference**: `onnxruntime.InferenceSession(..., providers=["CPUExecutionProvider"])`
   runs successfully at every batch size tested; `onnx.checker.check_model` passes on the exported graph.

Environment: Python 3.13.13, torch 2.11.0+cu128, onnx 1.22.0, onnxruntime 1.30.0, opset 17, Windows, this
development machine's CPU.

### Edge benchmark

| metric | value |
|---|---|
| parameters | 27,266 |
| ONNX file size | 127.0 KB |
| PyTorch CPU latency (default thread count, batch=1) | 12.36 ms/window |
| ONNX Runtime CPU latency (default thread count, batch=1) | 1.24 ms/window |
| PyTorch CPU latency (single-threaded, batch=1) | 9.94 ms/window |
| **ONNX Runtime CPU latency (single-threaded, batch=1)** | **0.319 ms/window** |
| ONNX Runtime throughput (single-threaded) | ~3,134 windows/s |

Both a "default threading" and a "single-threaded" number are reported, honestly, because they differ by a
large factor on this machine: a model this small (27k parameters, single-sample batches) is dominated by
multi-threaded dispatch overhead rather than compute, so the default (auto-detected, 8-thread) configuration
is *slower* per window than pinning both PyTorch and ONNX Runtime to one thread
(`torch.set_num_threads(1)`, `onnxruntime.SessionOptions().intra_op_num_threads = 1`). The single-threaded
number is the more representative one for Member 5's target: a lean C++20 + ONNX Runtime embedded
integration is unlikely to dedicate 8 CPU threads to a 127 KB model. Process memory was not reported: this
repo does not depend on `psutil` (see `CLAUDE.md`'s dependency-minimalism rule), and `src.inference.benchmark`
falls back to `None` when it isn't installed rather than adding it as a new requirement for one optional
number; model size and parameter count are exact and reproducible regardless.

Reproduce: `python scripts/export_onnx.py` writes the full report (this table's source) to
`experiments/m3_final_cnn_w40/final.onnx_report.json` (both `.onnx` and this report are untracked --
see `.gitignore` -- so this table is the durable record).

### Final leakage / causality audit (Milestone 4)

A full read-through of every Member 1 source file against the hard-rules checklist in `CLAUDE.md`
(vehicle/GPS leakage, train/test contamination, future information, session-boundary crossing, normalization
fit on val/test, augmentation applied to val/test, inference preprocessing mismatch, incorrect target scaling,
invalid uncertainty) found **no concrete bugs** -- the safeguards already built during Milestones 1-3 were
verified, not found broken:

- Leakage guard (`src/data/dataset.py::check_input_keys`) is enforced at the one place model inputs are
  assembled, not just documented; `tests/test_data.py` drives it with every forbidden field name.
- Normalization (`fit_normalization`) and the confidence reference (`set_confidence_reference`) are fit from
  **training** rows/labels/sigma only, in every script that calls them (`run_training.py`, `run_uncertainty.py`
  phase 4) -- re-confirmed by re-reading each call site.
- Augmentation (`build_augmentation`) is applied only to `train_x`, never to `val_x`/`test_x`, in
  `scripts/run_training.py::run_one`; the deterministic representation transform (`representation_transform`,
  identity except for `gravity_yaw`) is applied identically at train and eval/inference time.
- Windowing (`window_end_indices`/`assert_windows_valid`) rejects any window crossing a session boundary or a
  contiguity break, independently re-checked by a second, deliberately different code path.
- The test split (S-series) is touched exactly once by the model-selection pipeline (Milestone 3, phase 4);
  this milestone's `scripts/run_evaluation.py` reads the already-chosen final checkpoint against test again,
  which reproduces the same numbers (verified: MAE 4.786 m/s, matching `results/uncertainty/final_model.json`
  exactly) but does not change which model was chosen or fit anything new against test.
- **Inference preprocessing consistency, specifically**: `predict_contract` (PyTorch) and the new ONNX export
  path both call the SAME model object's `forward_full`, which owns normalization internally (there is no
  separate, independently-implemented preprocessing step in either inference path that could drift out of
  sync with training) -- confirmed by `tests/test_inference.py::test_onnx_matches_predict_contract_end_to_end`,
  which checks the two paths agree to float32 precision on real windows, not just that each looks correct in
  isolation.
- The heteroscedastic log-variance is clamped before every `exp()` (`VelocityNet.forward_full`), so
  `uncertainty` is finite and strictly positive by construction; the ONNX-exported graph reproduces this
  (see the PyTorch-vs-ONNX agreement table above, which includes `uncertainty`).
- Target scaling: `target_speed_mps` is already m/s (`configs/member1.yaml`'s `data.target_units: m/s`); no
  conversion bug is possible without changing that config value, which this milestone did not touch.

No source changes were needed as a result of this audit. The one known, already-documented limitation that
remains genuinely open is **test-set uncertainty calibration**: as reported in Milestone 3, the final model
is overconfident on the S-series test set (observed coverage below nominal at every level -- e.g. 47.2% of
test points fall within the predicted 1-sigma interval against the nominal 68%). This is a property of what
the model learned, not a pipeline bug, and it is not claimed to be fixed here -- `uncertainty` should still be
read as directionally informative rather than as a precisely-calibrated Gaussian interval; see the calibration
section above and `docs/member1_output_contract.md`.

### Consolidated ablations (Milestone 4, no retraining)

`scripts/run_ablation.py` reads `results/neural/results.json`, `results/neural_ablation_no_so3/results.json`
and `results/uncertainty/results.json` (all written by earlier milestones) and assembles one table per
ablation axis into `results/ablation/`: window size (2 s vs 4 s), augmentation on/off (SO(3) vs none, at each
window size and architecture), augmentation policy (none/so3/yaw/gravity_yaw, validation only, from Milestone
3 phase 1), and loss (NLL vs point, validation only, from Milestone 3 phase 3). No new numbers are produced --
see the milestone sections above for the numbers themselves and the reasoning behind each choice.

## Post-milestone-4 addendum: production 100 Hz contract correction

The project's production contract requires 100 Hz input consumed from Member 2's `AlignedIMUFrame` in a
200-sample (2-second) causal window, and an output contract field named `velocity_variance_m2s2` (not
`uncertainty`). Neither was true of Milestone 4's `m3_final_cnn_w40` deliverable (10 Hz-only input path,
4-second window, `uncertainty`-named sigma field). Full writeup: `docs/production_100hz.md`,
`docs/member1_output_contract.md`.

Fix: an additive Member 2 interface adapter (`src/inference/member2_interface.py`) that decimates Member 2's
genuine 100 Hz stream to the model's native 10 Hz resolution (no training data was fabricated), plus an
output-field rename (`uncertainty` sigma -> `velocity_variance_m2s2` = sigma²). Because the 200-sample/2-second
production window only decimates to a `window=20` model, a new checkpoint was trained at that window (the
`m3_final_cnn_w40` checkpoint above, at `window=40`, cannot serve a 2-second production buffer without either
retraining or a 400-sample buffer -- see `docs/production_100hz.md`).

**Freshly retrained and evaluated on the untouched S-series test set, same seed (42), same `yaw` augmentation
policy, same NLL loss as the table above:**

| Checkpoint | Window | Val MAE | Test MAE | Test RMSE | Test R² |
|---|---|---|---|---|---|
| `m3_final_cnn_w40` (reconfirmed unchanged; this addendum's own retrain) | 40 | 4.124 m/s | 4.786 m/s | 6.662 m/s | -0.052 |
| `production_cnn_w20` (new; serves the 100 Hz/200-sample production contract) | 20 | 4.364 m/s | 5.144 m/s | 7.249 m/s | -0.246 |

The `m3_final_cnn_w40` row above was reproduced bit-for-bit against the numbers already in this document
(Milestone 3's Phase 4 and Milestone 4's tables) by retraining with the identical config, seed and recipe --
confirming the production-contract fix did not silently change the existing, unchanged evaluation path. The
`production_cnn_w20` row is a genuinely new number, **worse** than `m3_final_cnn_w40` (test MAE +0.358 m/s,
~7.5% relative) -- the real, measured cost of matching the contract's literal 2-second window instead of the
4-second window Milestone 3 selected for best validation accuracy. This is not hidden: see
`docs/production_100hz.md` and the top-level `README.md` for both numbers side by side.

Both checkpoints' negative R² on this test split were already true before this change (see Milestone 3/4
above) -- the production checkpoint is not newly failing a bar the w40 model passed.

## Post-milestone-4 addendum #2: production accuracy-improvement pass

Focused ablation to reduce `production_cnn_w20`'s test MAE (5.144 m/s) while keeping the exact
production contract (window=20, 100 Hz Member 2 interface, output schema) unchanged. Protocol: seed 42
throughout; validation MAE selects candidates; the S-series test set is touched only once, for the
final selected candidate (see the note on C2/C3 below, which is the one place this session's actual
practice fell short of that rule).

### Diagnostic: target/IMU synchronization (checked before touching any preprocessing)

Cross-correlated `d(speed)/dt` (a finite-difference proxy) against each of the 6 IMU channels, per
session, over lags of ±10 samples. Correlations were weak (`|r| < 0.32` even at the best lag) and the
best lag was inconsistent across sessions (from -10 to +10, no common sign or magnitude) -- the
signature of unknown, per-trip phone mounting orientation (already documented,
`docs/data_protocol.md`), not a systematic timing/synchronization offset, which would show a
consistent lag across sessions. **No evidence of a synchronization bug; no preprocessing change made
on this basis.**

### Candidates (window=20 throughout; C0 is the pre-existing production baseline)

| id | architecture | loss | augmentation | features | params | val MAE | test MAE* | notes |
|---|---|---|---|---|---|---|---|---|
| C0 | cnn | nll | yaw | raw 6ch | 27,266 | 4.364 | 5.144 | baseline (`production_cnn_w20`) |
| C1 | tcn | nll | yaw | raw 6ch | 22,914 | 4.610 | -- | cited from the Phase 2 matrix above, not retrained (worse on val; test never touched) |
| C2 | cnn | huber (point, no uncertainty head) | yaw | raw 6ch | ~27,200 | 4.882 | 5.426 | worse; point loss clearly hurts at w20 (unlike w40, see Phase 3) |
| C3 | cnn | nll | none | raw 6ch | 27,266 | 4.656 | 5.525 | worse; confirms yaw augmentation still helps at w20 |
| C4 | cnn (channels=48) | nll | yaw | raw 6ch | 60,098 | 4.508 | not evaluated | worse despite 2.2x the parameters -- w20's accuracy ceiling isn't a capacity limit |
| **C5** | **cnn** | **nll** | **yaw** | **raw 6ch + `\|acc\|`/`\|gyr\|`** | **27,650** | **4.313** | **5.072** | **selected; `production_cnn_mag_w20`** |

\* C2 and C3 were run through `scripts/run_training.py`'s default CLI, which evaluates the test split
unconditionally -- their test MAE is reported above for transparency, but was **not** used to select or
rule out either candidate: both were already clearly worse than C0 on validation alone before their
test numbers existed. C4 and C5 were run with `evaluate_test=False` explicitly, so test was genuinely
untouched during their selection; C5 (the winner) was evaluated on test exactly once, after selection,
matching the intended protocol. This inconsistency is recorded here rather than glossed over.

C1's TCN-vs-CNN comparison, C2's point-vs-NLL-loss comparison and C3's yaw-vs-none-augmentation
comparison reproduce the same qualitative conclusions the Phase 2/3 milestone-3 matrix already reached
for window=40 (CNN beats TCN; augmentation helps; see above) -- at window=20 the loss-choice effect is
much larger (C2 costs 0.52 m/s val MAE vs. Phase 3's 0.03 m/s at w40), consistent with a shorter window
giving the heteroscedastic NLL objective less signal to separate "hard" from "easy" windows, so point
loss overfits harder here.

### Why C5 (magnitude channels) won

`docs/data_protocol.md` already documents that this dataset's phone mounting orientation is unknown and
inconsistent across trips -- the reason `yaw` augmentation exists at all. Per-axis accelerometer/gyro
values are therefore not directly comparable across sessions, but `|acc|` and `|gyr|` (vector norms)
are rotation-invariant by construction: the model does not have to learn that invariance from limited
data (only ~61k training windows), because it is given directly, at essentially zero parameter cost
(384 extra weights, all in the first conv layer). C0-C4 all operate purely on the per-axis raw signal
and/or vary capacity/loss/augmentation, none of which address this. Implementation: `test_magnitude_channels_are_rotation_invariant` (`tests/test_training.py`) checks the derived channels
are exactly rotation-invariant; `test_production_onnx_works_end_to_end_with_magnitude_channel_model`
(`tests/test_inference.py`) checks the production ONNX path still round-trips correctly with them.

### Final result (test set touched once, after selection)

| checkpoint | val MAE | test MAE | test RMSE | test R² | Δ test MAE vs. C0 |
|---|---|---|---|---|---|
| `production_cnn_w20` (C0, superseded) | 4.364 | 5.144 | 7.249 | -0.246 | -- |
| `production_cnn_mag_w20` (C5, **current production**) | 4.313 | 5.072 | 7.240 | -0.242 | **-0.072 m/s (-1.4%)** |

A real, reproducible, but modest improvement -- not a dramatic one. R² is still negative (barely
changed: -0.242 vs -0.246); this model still explains less test-set variance than predicting the mean
would, same as every window=20/40 model in this document. The unseen-group diagnostic (Vfa01/Vta1a/
Vta1b/Y1, never used for training/validation/model-selection) also improved: MAE 5.020 m/s vs C0's
5.187 m/s. Nothing here is claimed to close the gap with `m3_final_cnn_w40` (4.786 m/s test MAE) --
that gap is the documented cost of the contract's 2-second window (see the addendum above), and this
accuracy-improvement pass did not attempt to change the window length, which is fixed by the production
contract.

`production_cnn_w20`'s artifacts (checkpoint config, history, metrics, ONNX exports) are kept on disk
and referenced above rather than deleted, so this comparison remains reproducible.

## Post-milestone-4 addendum #3: error analysis and a second accuracy improvement

Continuation of addendum #2, starting from `production_cnn_mag_w20` (test MAE 5.072 m/s). Same
protocol: seed 42, validation selects candidates, test touched once for the final selection.

### Error breakdown of `production_cnn_mag_w20` on the S-series test set

| breakdown | worst segment | MAE there | best segment | MAE there |
|---|---|---|---|---|
| speed bin | [30, inf) m/s (n=2,277) | 26.4 | [0, 0.5) m/s (n=37,248) | 0.50 |
| by trip | S3c (n=37,158) | 8.39 | S4 (n=87,771) | 3.68 |
| turning (\|gyr_z\| at prediction point) | sharp turn >=0.6 rad/s (n=47) | 8.32 | straight <0.1 rad/s (n=291,153) | 5.06 |
| accel/braking (Δspeed over 0.3 s) | hard brake <-1 m/s (n=562) | 5.92 | accelerating [0.2,1) m/s (n=48,711) | 4.07 |

Per-sample MAE is worst at high speed and during sharp turns, as expected -- but **contribution to
overall MAE is dominated by volume, not by these worst-per-sample segments**: weighting each speed
bin's MAE by its share of the 301,580 test windows, the [5,10) and [10,15) m/s bins alone account for
~67% of the total 5.072 m/s MAE (1.89 + 1.51 m/s of the 5.07 total), while the rare >=25 m/s tail
(2.5% of windows) accounts for only ~9%. Turning and braking/acceleration events are both too rare
(<0.1% and ~0.3% of windows respectively for the "sharp"/"hard" buckets) to materially move the
overall number either way, and braking/accelerating windows are not markedly worse than steady-state
cruising. **Conclusion: the dominant error source is systematic underperformance in the common
5-15 m/s cruising range (58% of all test windows), not rare extreme-speed, turning or braking
events.** This is consistent with all R² values in this document being negative: a 2-second IMU-only
window carries a weak, easily-overfit signal for absolute cruising speed once a vehicle isn't actively
accelerating or braking (raw acceleration/gyro data doesn't distinguish "steady 8 m/s" from "steady
14 m/s" the way it distinguishes "accelerating" from "braking"), and this generalizes poorly to the
held-out S-series vehicles/trips.

### Candidate: longer heteroscedastic-NLL warmup

Hypothesis: heteroscedastic NLL training can reduce its own objective either by fitting the mean more
accurately *or* by predicting a larger variance for hard-to-fit inputs -- both lower the per-sample
NLL term. For the common, hard-to-fit cruising-speed windows identified above, the model may be taking
the "predict more uncertainty" path instead of the "fit harder" path. `training.nll_warmup_epochs`
controls how many initial epochs train the mean head alone (point loss) before the variance head
starts receiving gradient and this trade-off becomes available; lengthening it gives the mean head
more chance to fit those regions first.

| `nll_warmup_epochs` | val MAE | val RMSE | val R² | note |
|---|---|---|---|---|
| 3 (previous default, gen. 2) | 4.313 | 5.855 | -0.067 | `production_cnn_mag_w20` |
| **10** | **4.272** | **5.773** | **-0.037** | **selected; `production2_cnn_mag_w20`** |
| 15 | 4.334 | 6.114 | -0.163 | worse than both 3 and 10 |

Non-monotonic (10 beats both 3 and 15), so this is a genuine optimum found with 3 validation-only runs,
not the first improvement stopped at. No architecture or feature change; zero extra parameters; the
window=40 training recipe and every other config are untouched (`nll_warmup_epochs` was overridden
only for this window=20 run via the new `--nll-warmup-epochs` CLI flag on `scripts/run_training.py`).

### Final result (test set touched once, after selection)

| checkpoint | val MAE | test MAE | test RMSE | test R² | Δ test MAE vs. gen. 2 |
|---|---|---|---|---|---|
| `production_cnn_mag_w20` (gen. 2, superseded) | 4.313 | 5.072 | 7.240 | -0.242 | -- |
| `production2_cnn_mag_w20` (gen. 3, **current production**) | 4.272 | **4.927** | **7.020** | **-0.168** | **-0.145 m/s (-2.9%)** |

Combined with addendum #2's magnitude-channel change, the full chain from the original production
baseline is 5.144 -> 5.072 -> **4.927 m/s** (-4.2% total), closing most of the way to
`m3_final_cnn_w40`'s 4.786 m/s despite the window=20 constraint (down from an ~7.5% gap to ~3%). The
unseen-group diagnostic also improved further: MAE 4.899 m/s (gen. 3) vs 5.020 m/s (gen. 2) vs
5.187 m/s (gen. 1). R² is still negative -- this pass did not, and does not claim to, fix the
underlying cruising-speed information limitation identified above; it only reduced how much that
limitation costs in MAE. No further well-justified candidate was found this pass beyond the NLL-warmup
change; further gains likely require either more/varied training data (more vehicles, more genuine
speed variety at cruising speeds) or a longer window than the contract allows, neither of which is
addressable within this pass's constraints.

Both superseded checkpoints' artifacts are kept on disk and referenced above, not deleted.
