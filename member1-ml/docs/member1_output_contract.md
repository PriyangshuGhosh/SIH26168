# Member 1 output contract (for Member 3's adaptive EKF/UKF)

This is the schema Member 1's model emits for every prediction, and Member 3 consumes as a fusion
input. It is produced by `src/inference/predict.py::predict_contract` (PyTorch checkpoint) or,
equivalently, by the ONNX graph exported by `scripts/export_onnx.py` (see "ONNX export" below) --
both compute the same three numeric fields (`velocity_mps`, `velocity_variance_m2s2`, `confidence`)
from the same model, verified to agree to float32 precision (`docs/experiments.md`, Milestone 4).

## Schema

One record per prediction (one per causal IMU window, i.e. once every evaluation stride at
10 Hz -- see `docs/data_protocol.md`):

| Field | Type | Units | Range | Meaning |
|---|---|---|---|---|
| `velocity_mps` | float | m/s | `>= 0` | Predicted vehicle speed (the model's mean estimate). |
| `velocity_variance_m2s2` | float or `null` | m²/s² | `> 0`, or `null` | Predictive variance of `velocity_mps` (sigma², from the heteroscedastic Gaussian head). `null` for a model with no uncertainty head (`model.uncertainty is False`). |
| `confidence` | float or `null` | dimensionless | `(0, 1]`, or `null` | A bounded, monotonically-decreasing function of the predictive sigma (`null` exactly when `velocity_variance_m2s2` is `null`). Convenience only -- `velocity_variance_m2s2` carries the same information in physical units and should be preferred wherever the fusion filter can use a variance directly. |
| `timestamp` | float | caller-defined | -- | The timestamp of the last IMU sample in the window (the prediction point), in whatever time base the caller's IMU stream uses. This module does not fabricate a clock: it passes through the timestamps the caller supplies. |

Example (uncertainty-enabled model):

```json
{"velocity_mps": 8.42, "velocity_variance_m2s2": 1.32, "confidence": 0.71, "timestamp": 1234.7}
```

Example (point-only model, or before Milestone 3's uncertainty head exists):

```json
{"velocity_mps": 8.42, "velocity_variance_m2s2": null, "confidence": null, "timestamp": 1234.7}
```

**Member 3 must treat `null` as "no confidence-aware fusion information available" and fall back to
its own default noise model** for that input -- never assume a numeric default such as `0` or `1`.

## Definitions

- **`velocity_mps`**: `target_mean + target_std * mean_head(features)`, clamped to `>= 0` (see
  `docs/architecture.md`). Units are m/s, matching the training target (`target_speed_mps`, already
  m/s in the current dataset -- see `docs/data_protocol.md`).
- **`velocity_variance_m2s2`**: `sigma ** 2`, where `sigma = exp(0.5 * log_var)` and `log_var` is the
  model's clamped, native-units heteroscedastic log-variance (see `docs/architecture.md`'s
  uncertainty section). It is the variance of a Gaussian predictive distribution over the true speed,
  i.e. Member 3 can use `velocity_variance_m2s2` directly as an observation-noise variance in its
  filter, or combine it with the filter's own process/measurement noise however is appropriate for
  the fusion design.
- **`confidence`**: `1 / (1 + sigma / confidence_ref_sigma)` where `sigma = sqrt(velocity_variance_m2s2)`,
  and `confidence_ref_sigma` is the median predictive sigma on the model's own TRAINING data, fit
  once after training and stored as a checkpoint buffer (`VelocityNet.confidence_ref_sigma`, set by
  `set_confidence_reference`) -- no separate config value is needed at inference time.
  `confidence == 1` at `sigma == 0`, `confidence == 0.5` at `sigma == confidence_ref_sigma`, and
  `confidence -> 0` as `sigma` grows. It is a convenience field for consumers that want a single
  bounded number rather than a variance; it carries no information `velocity_variance_m2s2` doesn't
  already have.

## What this contract deliberately does NOT define

- **Fusion logic.** How Member 3's EKF/UKF weights or gates `velocity_mps` by
  `velocity_variance_m2s2` is Member 3's responsibility, not Member 1's.
- **A wall-clock time base.** `timestamp` is opaque to this module; whatever clock the live IMU
  stream uses at deployment time is what ends up here. In this repo's own evaluation code, it is
  `t_session_s` (session-relative seconds), because that is the only timestamp the dataset provides.
  Neither `predict_contract` nor the ONNX graph produces a `timestamp` output -- the caller supplies
  it in both cases.
- **Member 3's/Member 5's fusion or embedded-integration code.** This repo only produces the
  contract's numeric fields and exports the model that produces them; consuming those fields in an
  EKF/UKF, or wiring the ONNX graph into a C++20 application, is downstream of this repo.

## ONNX export

`scripts/export_onnx.py` exports the checkpoint above to `experiments/m3_final_cnn_w40/final.onnx`
(untracked, like every other checkpoint artifact -- see `.gitignore`) and verifies it: dynamic batch
size, finite/in-range outputs, and PyTorch-vs-ONNX-Runtime numerical agreement to within
`atol=1e-4, rtol=1e-3` (measured max abs diff on real validation windows, under the field's previous
name `uncertainty` (sigma, before the field was renamed to `velocity_variance_m2s2` = sigma² for
production-contract compliance -- see "Production input" below): 1.91e-5 for `velocity_mps`,
6.20e-6 for sigma, 3.28e-7 for `confidence` -- see `docs/experiments.md`'s Milestone 4 section for the
full table and CPU latency numbers).

The exported ONNX graph takes the identical `[B, T, 6]` float32 IMU-window input (`T = 40`, dynamic
batch) and returns exactly `velocity_mps`, `velocity_variance_m2s2`, `confidence` as separate output
tensors, in that order, computed by the same math as `predict_contract` above (see
`docs/architecture.md`'s "ONNX export and edge benchmark" section for how the exported graph is
constructed). `timestamp` is never a model output, in ONNX or in PyTorch -- attach it from the
caller's own IMU stream timestamps after running inference, exactly as `predict_contract` does. This
graph is the artifact Member 5 integrates via C++20 + ONNX Runtime (CPU execution provider);
`src/inference/benchmark.py` reports its CPU latency, throughput, size and parameter count.

## Production input (100 Hz Member 2 `AlignedIMUFrame`)

The above (`export_model`, native `[B, T, 6]` at `T ∈ {20, 40}`) is Member 1's own evaluation/export
path, driven by the project's 10 Hz training data. The project's production input contract is 100 Hz,
consuming Member 2's `AlignedIMUFrame` directly in a 200-sample (2 s) causal window. Because no
genuine 100 Hz training data exists (see `docs/production_100hz.md` for the full explanation),
`src/inference/member2_interface.py` and `src/inference/export_onnx.py::export_production_model`
provide this as an additive adapter -- decimating the real 100 Hz stream to the model's native 10 Hz
resolution rather than retraining on fabricated data -- exposed as
`scripts/export_onnx.py --production` (requires a `window=20` checkpoint). The output contract fields
(`velocity_mps`, `velocity_variance_m2s2`, `confidence`, `timestamp`) are identical; only the input
side differs. **Production-path accuracy against real 100 Hz data has not been measured** (no such
data exists in this repo) -- see `docs/production_100hz.md`'s "What is and is not validated" section.

## Producing the contract

```python
from src.training.train import load_checkpoint, resolve_device
from src.inference.predict import predict_contract

model, payload = load_checkpoint("experiments/m3_final_<arch>_w<window>/final.pt")
records = predict_contract(model, imu, ends, window, timestamps, device=resolve_device())
```

`imu` is the `(N, 6)` array from `src.data.dataset.load_npz(...).imu` (or an equivalent live IMU
buffer), `ends` are causal window end row-indices (`src.data.windowing.window_end_indices`), and
`window` is the model's window length (20 or 40 samples, i.e. 2 s or 4 s at 10 Hz). If the model was
trained with the `"gravity_yaw"` augmentation/representation policy, pass
`transform=src.data.augmentation.representation_transform("gravity_yaw")` -- see
`docs/architecture.md` and the model's `metrics.json` / `results/uncertainty/final_model.json` for
which policy the shipped checkpoint actually uses.

Or, via the exported ONNX graph (Python shown for parity; the same graph is what Member 5 loads in
C++20 + ONNX Runtime):

```python
import onnxruntime as ort

session = ort.InferenceSession("experiments/m3_final_cnn_w40/final.onnx", providers=["CPUExecutionProvider"])
velocity_mps, velocity_variance_m2s2, confidence = session.run(None, {"imu_window": windows})  # windows: float32 [B, 40, 6]
# attach `timestamp` yourself, e.g. one entry per window from your own IMU stream's clock
```

Or, via the production ONNX graph (raw Member 2 100 Hz input, decimated inside the graph):

```python
import onnxruntime as ort

session = ort.InferenceSession("experiments/m3_final_cnn_w20.production.onnx", providers=["CPUExecutionProvider"])
velocity_mps, velocity_variance_m2s2, confidence = session.run(None, {"imu_window_100hz": raw_windows})
# raw_windows: float32 [B, 200, 6], channel order [ax_v, ay_v, az_v, gx_v, gy_v, gz_v], 2 s at 100 Hz
```
