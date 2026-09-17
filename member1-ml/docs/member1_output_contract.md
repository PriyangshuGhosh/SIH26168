# Member 1 output contract (for Member 3's adaptive EKF/UKF)

This is the schema Member 1's model emits for every prediction, and Member 3 consumes as a fusion
input. It is produced by `src/inference/predict.py::predict_contract` (PyTorch checkpoint) or,
equivalently, by the ONNX graph exported by `scripts/export_onnx.py` (see "ONNX export" below) --
both compute the same three numeric fields (`velocity_mps`, `uncertainty`, `confidence`) from the
same model, verified to agree to float32 precision (`docs/experiments.md`, Milestone 4).

## Schema

One record per prediction (one per causal IMU window, i.e. once every evaluation stride at
10 Hz -- see `docs/data_protocol.md`):

| Field | Type | Units | Range | Meaning |
|---|---|---|---|---|
| `velocity_mps` | float | m/s | `>= 0` | Predicted vehicle speed (the model's mean estimate). |
| `uncertainty` | float or `null` | m/s | `> 0`, or `null` | Predictive standard deviation (sigma) of `velocity_mps`, from the heteroscedastic Gaussian head. `null` for a model with no uncertainty head (`model.uncertainty is False`). |
| `confidence` | float or `null` | dimensionless | `(0, 1]`, or `null` | A bounded, monotonically-decreasing function of `uncertainty` (`null` exactly when `uncertainty` is `null`). Convenience only -- `uncertainty` carries the same information in physical units and should be preferred wherever the fusion filter can use a variance directly. |
| `timestamp` | float | caller-defined | -- | The timestamp of the last IMU sample in the window (the prediction point), in whatever time base the caller's IMU stream uses. This module does not fabricate a clock: it passes through the timestamps the caller supplies. |

Example (uncertainty-enabled model):

```json
{"velocity_mps": 8.42, "uncertainty": 1.15, "confidence": 0.71, "timestamp": 1234.7}
```

Example (point-only model, or before Milestone 3's uncertainty head exists):

```json
{"velocity_mps": 8.42, "uncertainty": null, "confidence": null, "timestamp": 1234.7}
```

**Member 3 must treat `null` as "no confidence-aware fusion information available" and fall back to
its own default noise model** for that input -- never assume a numeric default such as `0` or `1`.

## Definitions

- **`velocity_mps`**: `target_mean + target_std * mean_head(features)`, clamped to `>= 0` (see
  `docs/architecture.md`). Units are m/s, matching the training target (`target_speed_mps`, already
  m/s in the current dataset -- see `docs/data_protocol.md`).
- **`uncertainty`**: `sigma = exp(0.5 * log_var)`, where `log_var` is the model's clamped,
  native-units heteroscedastic log-variance (see `docs/architecture.md`'s uncertainty section). It
  is the standard deviation of a Gaussian predictive distribution over the true speed, i.e. Member 3
  can use `uncertainty ** 2` directly as an observation-noise variance in its filter, or combine it
  with the filter's own process/measurement noise however is appropriate for the fusion design.
- **`confidence`**: `1 / (1 + uncertainty / confidence_ref_sigma)`, where `confidence_ref_sigma` is
  the median predictive sigma on the model's own TRAINING data, fit once after training and stored
  as a checkpoint buffer (`VelocityNet.confidence_ref_sigma`, set by `set_confidence_reference`) --
  no separate config value is needed at inference time. `confidence == 1` at `uncertainty == 0`,
  `confidence == 0.5` at `uncertainty == confidence_ref_sigma`, and `confidence -> 0` as `uncertainty`
  grows. It is a convenience field for consumers that want a single bounded number rather than a
  variance; it carries no information `uncertainty` doesn't already have.

## What this contract deliberately does NOT define

- **Fusion logic.** How Member 3's EKF/UKF weights or gates `velocity_mps` by `uncertainty` is
  Member 3's responsibility, not Member 1's.
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
`atol=1e-4, rtol=1e-3` (measured max abs diff on real validation windows: 1.91e-5 for `velocity_mps`,
6.20e-6 for `uncertainty`, 3.28e-7 for `confidence` -- see `docs/experiments.md`'s Milestone 4
section for the full table and CPU latency numbers).

The exported ONNX graph takes the identical `[B, T, 6]` float32 IMU-window input (`T = 40`, dynamic
batch) and returns exactly `velocity_mps`, `uncertainty`, `confidence` as separate output tensors, in
that order, computed by the same math as `predict_contract` above (see `docs/architecture.md`'s
"ONNX export and edge benchmark" section for how the exported graph is constructed). `timestamp` is
never a model output, in ONNX or in PyTorch -- attach it from the caller's own IMU stream timestamps
after running inference, exactly as `predict_contract` does. This graph is the artifact Member 5
integrates via C++20 + ONNX Runtime (CPU execution provider); `src/inference/benchmark.py` reports its
CPU latency, throughput, size and parameter count.

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
velocity_mps, uncertainty, confidence = session.run(None, {"imu_window": windows})  # windows: float32 [B, 40, 6]
# attach `timestamp` yourself, e.g. one entry per window from your own IMU stream's clock
```
