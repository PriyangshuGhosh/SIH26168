# Production input: Member 2's genuine 100 Hz interface

This page documents how Member 1 meets the project's production input contract (100 Hz vehicle-frame
IMU, 200-sample / 2-second causal window, consuming Member 2's `AlignedIMUFrame`) given that **no
genuine 100 Hz training data exists in this repository**, and why the fix is a resampling *interface*,
not a retrained model.

## The constraint

- `data/member1_imu_speed.npz` (the only dataset this project trains or evaluates on) is natively and
  consistently sampled at **10 Hz** -- verified per-session by `src.data.inspect_dataset` (median
  `dt` in `[0.0996, 0.1006]` s across all 34 sessions, no exceptions; see `docs/data_protocol.md`).
- There is no raw 100 Hz capture, resampling script, or alternate dataset anywhere in this repo or in
  the IO-VNBD-derived data delivered for this project.
- Member 2 (`docs/member2/INTEGRATION.md`) genuinely runs at 100 Hz in production
  (`FrameAlignerConfig.sample_rate_hz == 100.0`, `sih26168_alignment.types`).

Upsampling the 10 Hz training data to synthesize "100 Hz" windows was deliberately **not** done: every
interpolated sample would be information the sensor never produced, and a model trained on such
windows would silently claim resolution it does not have. That is the failure mode this design avoids.

## The fix: decimate the real 100 Hz stream, don't fabricate training data

The resolution goes the other, honest direction. Member 2's real 100 Hz `AlignedIMUFrame` stream is
**decimated** down to the 10 Hz resolution the shipped model actually understands, keeping the most
recent real sample of every 10 (`raw[9::10]`) -- never an interpolated or averaged value, exactly the
samples a genuine 10 Hz sensor would have produced at those instants. This is implemented in
`src/inference/member2_interface.py`:

- `ProductionWindowBuffer`: a causal ring buffer that accepts `AlignedIMUFrame`-like objects at
  100 Hz, gates on `status == FULLY_ALIGNED` (resetting on any other status, per
  `docs/member2/INTEGRATION.md`), and emits a raw `[200, 6]` window (200 samples = 2 s at 100 Hz, the
  production contract's window) every `stride` frames (default 10, i.e. one emission per 100 ms,
  matching `docs/WORK_DISTRIBUTION.md`'s "recommended prediction stride: 10 samples").
- `decimate` / `production_window_to_model_input`: turn that raw `[200, 6]` window into the `[20, 6]`
  tensor (2 s at 10 Hz) the model was actually trained and evaluated on.
- `src/inference/export_onnx.py::ProductionInferenceModule` / `export_production_model`: bake the same
  decimation into the exported ONNX graph itself, so the graph Member 5 loads takes the literal
  production shape `[B, 200, 6]` and internally reduces to `[B, 20, 6]` before running the unchanged
  trained convolutional blocks.

**`src/models/tcn_velocity.py` (the CNN/TCN architecture, including the uncertainty head) is completely
unchanged**, as is the training/evaluation pipeline (`src/data/*`, `src/training/*`,
`src/evaluation/*`). Only a new, additive inference-time adapter was introduced.

## Why window = 20 (2 s), not window = 40 (4 s)

`configs/member1.yaml` trains both `window: 20` (2 s) and `window: 40` (4 s) variants; the milestone-3
final selection (`docs/experiments.md`) picked `cnn_w40` for better validation MAE. The production
contract specifies a 200-sample / 2-second window, which after decimation by 10 is exactly 20 samples
-- **not** 40 (a 4-second production window would need a 400-sample raw buffer). Rather than retrain
or silently deviate from the literal contract, the production path requires a `window=20` checkpoint:
`export_production_model` and `ProductionInferenceModule` both raise `ValueError` if asked to serve a
window that doesn't decimate exactly to 200 raw samples. The `window=40` checkpoint remains fully
supported for non-production use (`export_model`, `scripts/export_onnx.py` without `--production`).

**This has a real, measured accuracy cost, not a hidden one** (both numbers below are freshly
retrained and evaluated on the untouched S-series test set, same seed, same `yaw` augmentation policy,
same NLL loss -- reproduce with the commands in "Reproducing these numbers" below):

| Checkpoint | Window | Val MAE | Test MAE | Test RMSE | Test R² |
|---|---|---|---|---|---|
| `experiments/m3_final_cnn_w40` (existing milestone-3 final, native/offline use) | 40 (4 s @ 10 Hz) | 4.124 m/s | **4.786 m/s** (17.23 km/h) | 6.662 m/s | -0.052 |
| `experiments/production_cnn_w20` (new, serves the 100 Hz / 200-sample production contract) | 20 (2 s @ 10 Hz, decimated from 200 @ 100 Hz) | 4.364 m/s | **5.144 m/s** (18.52 km/h) | 7.249 m/s | -0.246 |

The production checkpoint is **~7.5% worse test MAE** than the window=40 model -- the real cost of
matching the contract's literal 2-second window instead of the milestone-3-selected 4-second one. Both
R² values are negative on this held-out test split (the model explains less test-set variance than
predicting the mean would), consistent with what `docs/experiments.md` already reported for the w40
model -- this was already a known, documented limitation before this change, not introduced by it.

### Reproducing these numbers

```bash
python scripts/run_training.py --archs cnn --windows 20 --uncertainty --augmentation yaw \
    --tag production --results-dir results/production
python scripts/finalize_production_checkpoint.py   # fits confidence_ref_sigma, writes final.pt
python scripts/run_evaluation.py --checkpoint experiments/production_cnn_w20/final.pt --window 20 \
    --augmentation-policy yaw --splits train val test unseen \
    --out results/evaluation/final_production_cnn_w20.json
```

## What is and is not validated

Two different things are validated separately here -- keep them distinct:

1. **The `window=20` model's own accuracy, at its native 10 Hz resolution.** This IS validated: it is
   the same real S-series test set, same leakage-safe split, same evaluation code as every other
   number in `docs/experiments.md`. Test MAE 5.144 m/s (see the table above). This is a real,
   measured accuracy number, not a placeholder.
2. **The production adapter's (buffer + decimation + ONNX graph) plumbing correctness.** Also
   validated, by unit tests (`tests/test_member2_interface.py`, `tests/test_inference.py`): buffer
   gating/reset/stride/causality, decimation correctness, structural compatibility with the real
   `sih26168_alignment.AlignedIMUFrame` dataclass (imported directly, not reimplemented), the
   production ONNX graph's shape/finiteness/value-range and PyTorch-vs-ONNX numerical agreement --
   all on synthetic data, because there is no real 100 Hz recording to run it on.
3. **NOT validated: end-to-end accuracy of (1) run through (2) against a real 100 Hz Member 2
   stream.** No genuine 100 Hz recording exists in this repo, so there is no way to measure whether
   decimating a *real* 100 Hz stream produces the same distribution of 10 Hz-equivalent samples as
   the model's actual (natively 10 Hz) training data. `scripts/export_onnx.py --production`'s
   verification report says so explicitly (its `"note"` field) rather than presenting synthetic-only
   checks as a real-world accuracy guarantee. If genuine 100 Hz recordings become available, the
   honest next step is retraining natively on them (a like-for-like comparison against the decimation
   approach), not assuming decimation is accuracy-neutral.
