# Long-GNSS-blackout investigation: a stateful Member 1 candidate

## Background

The GNSS-blackout drift benchmark (`member5_engine/scripts/gnss_blackout_benchmark.py`) showed that
after fixing a real Member 2 calibration-threshold defect, drift passed at 50 m (7.4%) but failed at
1 km (215%). Root cause, confirmed directly against the committed production ONNX model
(`experiments/production2_cnn_mag_w20/final.production.onnx`): fed a clean, synthetic, near-zero
longitudinal-acceleration window (a realistic steady-cruise signature) at several different assumed
true speeds, the model predicts **~0 m/s with low variance** every time -- confidently wrong,
regardless of the true speed. This is architectural, not a training bug: `cnn`/`cnn_mag`/`tcn` are
all **stateless between calls** -- each 2-second causal window is processed from scratch, with no way
to carry forward anything learned from an earlier acceleration event. Constant velocity is physically
indistinguishable from rest using acceleration data alone once a window has no transient content
(Galilean invariance) -- no architecture *within a fixed window* can escape this. Member 3's NIS gate
correctly rejects these wrong measurements (this is not a bug to "loosen"), so once a blackout is
both GNSS-denied and low-excitation for longer than the model's receptive field, the system reverts
to unaided inertial dead reckoning, whose bias-driven drift grows essentially unbounded.

## Candidate architectures considered

| Criterion | GRU (chosen) | LSTM | Causal TCN + memory token | Exotic SSM (S4/Mamba-lite) |
|---|---|---|---|---|
| Causal | yes (recurrent by construction) | yes | yes, with a custom extra input | yes |
| True cross-call memory | yes -- hidden state is a first-class tensor | yes, but cell+hidden state (2x the state to carry) | only as much as the "memory token" design captures; non-standard, unverified | yes, but exotic |
| 10 Hz native / 100 Hz production input | yes, same decimation as existing production interface | yes | yes | yes |
| CPU latency | very low -- one GRU cell step per 10 Hz tick, no 200-sample window replay | low, marginally higher than GRU (extra gate) | window replay still needed unless redesigned | unclear, no established lightweight mobile runtime |
| Model size | very small (8-40 K params here) | small, ~1.3x GRU for equal hidden size | similar to existing cnn/tcn plus new head | model-dependent, generally larger |
| ONNX / mobile compatibility | standard, well-supported streaming-RNN ONNX pattern (explicit `h_in`/`h_out`) | same as GRU, one more state tensor | non-standard graph, unverified ORT/mobile support | poor -- typically needs custom ops, not verified exportable here |
| Uncertainty head | same linear heteroscedastic head as `VelocityNet`, unchanged | same | would need a redesign | would need a redesign |
| M3 compatibility | unchanged: still emits `velocity_mps`/`velocity_variance_m2s2` per tick | unchanged | unchanged | unchanged |

GRU was chosen: it is the simplest architecture that provides genuine, unbounded cross-call memory
(the property actually needed here), has half the recurrent state of an LSTM for equivalent capacity
(cheaper on an edge CPU, simpler ONNX I/O), and slots into the existing `VelocityNet` class with
minimal new code (see `src/models/tcn_velocity.py`: `arch="gru"`). LSTM was not built and benchmarked
end-to-end given the time budget for this investigation; it is the natural fallback if GRU's
generalisation turns out to be the bottleneck in further work, not a fundamentally different answer
to the "does statefulness help" question this investigation was about. The TCN-with-memory-token and
SSM options were rejected without training a model: neither has an established, low-risk ONNX/mobile
deployment path, and the SIH constraint is a real smartphone CPU running ONNX Runtime.

## Training: two very different results from the same architecture

**Attempt 1 (`scripts/run_training.py --archs gru`, reusing the existing windowed pipeline exactly
like cnn/tcn):** hidden state is reset to zero at the start of every independent, randomly-strided
2-second training window (`src/data/windowing.py`'s existing, correct, leakage-safe contract).
Checkpoint: `experiments/m1_gru_gru_w20/best.pt`. Result: test MAE 5.61 m/s, worse than
`production2_cnn_mag_w20`'s 4.93 m/s, and -- checked directly with `VelocityNet.step` -- after a
10-second, 1.2 m/s^2 acceleration event it still predicts ~0.01 m/s. Reusing the windowed pipeline
gives the model no gradient signal that ever rewards remembering anything past 2 seconds, so it
learns nothing an RNN wasn't already capable of before: same failure as cnn/tcn.

**Attempt 2 (`scripts/train_gru_streaming.py`, truncated-BPTT over whole sessions):** trains on
session-contiguous IMU sequences (same trip-family train/val/test split, no group leakage -- see
`src/data/splits.py`, unchanged), carrying the GRU's hidden state across chunks *within* a session
(TBPTT, `--chunk-steps 300`), resetting only at genuine session boundaries, and supervising the loss
at **every** 10 Hz row with the real `target_speed_mps` label (not just window-end points). Checkpoint:
`experiments/m1_gru_stream2_gru_w20/best.pt`. Directly tested: after the same 10 s / 1.2 m/s^2
acceleration event, the model correctly estimates ~11.2 m/s (true ~12), and holds ~11.18 m/s through
90 seconds of subsequent zero-acceleration "silent cruise" -- a <1% decay, versus collapsing to zero
immediately for every stateless model tested.

No GPS, vehicle-side speed, OBD/CAN, future samples, or grouping columns were used as model inputs at
any point (`src/data/dataset.py`'s `ALLOWED_INPUT_KEYS`/`check_input_keys` leakage guard, unchanged,
covers both training scripts since both build model input from `acc`/`gyr` only).

## Results

### M1 regression metrics (test split, real IO-VNBD-derived data)

| Metric | production2_cnn_mag_w20 (current) | GRU, streaming-trained (new) |
|---|---:|---:|
| Test MAE | 4.93 m/s | 5.73-5.86 m/s (windowed or streaming eval) |
| Test RMSE | 7.03 m/s | 7.04-8.24 m/s |
| Test R^2 | -0.17 | -0.18 to -0.61 |
| Stationary MAE | 0.44 m/s | 11.27-11.45 m/s (regression -- see limitations) |
| Steady-speed MAE | 6.73 m/s | 4.92-4.95 m/s (improvement) |
| Uncertainty | trained heteroscedastic NLL, documented as overconfident on held-out trips | **not meaningfully trained** -- only 1 point-loss epoch survived early stopping before any NLL epoch ran; `velocity_variance_m2s2` is the untrained flat prior (see Limitations) |

The streaming GRU is **not** a strictly better drop-in replacement for the CNN on aggregate accuracy:
it is worse overall and substantially worse at detecting a genuine stop (stationary MAE regression),
almost certainly because it only received ~4 epochs of training (early-stopped) against a model that
had three milestones of tuning. It is better specifically at steady-speed tracking, the regime
diagnosed as the actual root cause of long-blackout drift.

### Navigation (GNSS-blackout benchmark, same synthetic scenario, same seed)

| Metric | Current (windowed CNN) | New (streaming GRU) |
|---|---:|---:|
| 50 m blackout drift | 7.44% | **1.71%** |
| 1 km blackout drift | 215.2% (FAIL) | **3.47%** (PASS) |
| 1271 m / 96 s blackout drift | 296.0% (FAIL) | **0.03%** (PASS) |

See `results/blackout_plots/trajectory_reference_vs_estimated.png` and `error_vs_distance.png`
(generated by `member5_engine/scripts/plot_blackout_trajectories.py`).

## Stationary-MAE fix: two attempts, both rejected

`scripts/train_gru_streaming.py` now supports a `STATIONARY_WEIGHT` loss reweighting (upweights rows
with true speed `< STATIONARY_WEIGHT_THRESHOLD_MPS` in the huber/NLL loss -- a standard weighted-
regression technique, not a hardcoded/clamped output). Two settings were tried, both trained for
several epochs including a genuine NLL phase:

| Weight | Stationary MAE (streaming) | Steady-speed MAE (streaming) | Silent-cruise persistence test |
|---|---:|---:|---|
| 0 (final candidate, `m1_gru_stream2_gru_w20`) | 11.27 m/s | **4.95 m/s** | holds ~11.2 m/s through 90 s of zero accel |
| 3.0 | 1.19-1.36 m/s | 8.47-8.5 m/s | not directly retested (checkpoint superseded) |
| 1.5 | 0.72-0.88 m/s | 7.81-9.24 m/s | **collapses to ~ -0.25 m/s within the 90 s window -- broken** |

Both weighted attempts measurably improved stationary detection (and the 1.5 run also completed the
NLL phase, giving a real, non-flat-prior uncertainty head) but **materially broke the exact
capability this investigation exists to deliver**: re-run through the same 10 s-acceleration-then-90
s-silent-cruise test used throughout this document, the 1.5-weighted checkpoint's velocity estimate
decayed back toward zero (and briefly went negative) instead of holding, i.e. it regressed to the
same failure mode as the stateless CNN. Per the explicit instruction governing this pass ("if a
change improves one metric but materially breaks another, reject it"), **both reweighted checkpoints
were rejected and deleted**; `m1_gru_stream2_gru_w20` (the original, unweighted, single-epoch
checkpoint) remains the final candidate. Its stationary-MAE regression (11.27 m/s vs. the CNN's
0.44 m/s) and untrained uncertainty head (flat prior; NLL phase never reached in the accepted
checkpoint) are therefore **still open, not fixed in this pass** -- see "Remaining work" below for
what a real fix would need.

An intermediate per-epoch checkpoint that might have balanced both objectives better than either
epoch 1 (weight 0) or the final epoch of the weighted runs (weight 1.5) cannot be recovered:
`train_gru_streaming.py` only ever keeps the single best-by-selection-score checkpoint on disk, not a
snapshot per epoch. A revised version of that script that keeps a small rolling window of recent
checkpoints would let a future attempt pick a better point on this tradeoff without retraining from
scratch -- noted as a tooling gap, not implemented here per the "do not keep iterating" instruction
for this pass.

## Limitations (honest, not glossed over)

1. **Uncertainty is not usable from the accepted checkpoint.** `m1_gru_stream2_gru_w20` trained only
   1 real epoch before early stopping, entirely within the point-loss warmup phase, so the
   heteroscedastic head never left its zero-init flat prior. The one checkpoint that did reach a
   stable NLL phase (`STATIONARY_WEIGHT=1.5`) was rejected for breaking silent-cruise persistence
   (see above). `velocity_variance_m2s2`/`confidence` from the accepted checkpoint should be treated
   as an uninformative constant, not a calibrated signal -- Member 3's NIS gate will still function
   (a constant variance is still a valid, if uninformative, measurement noise estimate), but it is
   not "meaningful and usable" in the sense of reflecting per-prediction confidence.
2. **Stationary/stopped-vehicle detection regressed** (0.44 -> 11.27 m/s MAE) and **remains
   regressed** in the final accepted checkpoint -- see above for the two fix attempts and why both
   were rejected.
3. **Training instability / non-reproducible wall-clock time.** Multiple runs on this machine showed
   large, unexplained slowdowns (one run's per-epoch time varied from ~180 s to effective multi-hour
   stalls with no code change) not obviously tied to disk space, chunk size, or loss function;
   root cause not identified. Epoch count and early-stopping behaviour are reproducible given a
   fixed seed and a machine without this slowdown; wall-clock time is not.
4. **Only one architecture (GRU) was actually trained end-to-end**; LSTM and other alternatives were
   compared analytically, not empirically (see comparison table).
5. This is a **simulation** validation of the navigation benefit (no real GPS-tagged trajectory exists
   in this repository -- see the M1-vs-M5 audit's Phase 1). The M1 regression metrics above, by
   contrast, **are** real IO-VNBD-derived-data results (type A), not simulated.
6. **C++ production integration (`member5_engine`) is written but NOT build/test verified.** This
   sandbox has no C++ compiler. `ISpeedEstimator::reset()` (new, default no-op, non-breaking),
   `GruStreamingSpeedEstimator` (new, in `SpeedEstimator.hpp`/`.cpp`), and `Engine::loadSpeed`'s new
   opt-in `"gru:"` path prefix (existing default `OnnxSpeedEstimator` path is untouched) were
   written by careful manual mirroring of `OnnxSpeedEstimator`'s exact patterns and manual review,
   not compiled or run. **Do not treat this as validated** until it is built and exercised
   (`ctest -R member5`, `synthetic_e2e`) on a machine with the toolchain. The Python-side integration
   (`GruStreamingSpeedSource` in `member5_engine/scripts/gnss_blackout_benchmark.py`) and the
   stateful ONNX export (verified PyTorch<->ONNX agreement ~2e-6) ARE real and tested -- only the C++
   wiring is unverified.

## Remaining work / bottleneck if further drift reduction or a production-ready M1 is wanted

The measured 1 km/1271 m navigation results already pass the SIH <10% bound with the accepted
checkpoint, so no further architecture change is required to meet the *stated navigation* benchmark.
What is NOT resolved, and would need real further work (not attempted further in this pass, per
instruction):
- **Stationary detection + calibrated uncertainty, without breaking silent-cruise persistence.** Two
  single-parameter loss-reweighting attempts both failed to get both properties at once. A
  fundamentally different mechanism is more likely to work than a third weight value: e.g. a small
  auxiliary "is the vehicle stopped" signal (from Member 2's own `STATIC_DETECTED` status, already
  computed) gating the GRU's output toward zero only when that external signal is confidently true,
  rather than asking one regression loss to learn both "trust accumulated momentum" and "abandon it
  instantly on a real stop" from IMU alone.
- Checkpoint every epoch (not just best-by-score) during training so a human can inspect the full
  tradeoff curve and pick a point on it, instead of re-running training for each candidate weight.
- The single most valuable data improvement would be **real GPS-tagged trajectories** (this repo's
  IO-VNBD subset has real speed labels but no position ground truth at all), which would let this
  investigation move from simulation-based navigation validation (type B) to real GNSS-tagged
  trajectory validation (type C), and would give the training pipeline a much larger set of
  sustained-cruise segments than the current 34-session dataset provides.
- Build and test the C++ integration on a machine with a compiler; it is written but unverified.

## Reproduce

```bash
cd member1-ml
# M1 training (streaming GRU, ~4 epochs, ~10 min on CPU)
python scripts/train_gru_streaming.py --max-epochs 9 --point-warmup-epochs 8 --chunk-steps 300 \
    --lr 1e-3 --patience 3 --tag m1_gru_stream2 --device cpu

# M1 regression comparison (windowed + streaming + regime breakdown)
python scripts/evaluate_regimes.py \
    --checkpoints experiments/production2_cnn_mag_w20/best.pt experiments/m1_gru_stream2_gru_w20/best.pt
python scripts/evaluate_gru_streaming.py --checkpoint experiments/m1_gru_stream2_gru_w20/best.pt

# GNSS-blackout benchmark, both M1 candidates
python ../member5_engine/scripts/gnss_blackout_benchmark.py --m1-model onnx
python ../member5_engine/scripts/gnss_blackout_benchmark.py --m1-model gru-streaming

# Position plots
python ../member5_engine/scripts/plot_blackout_trajectories.py --out-dir results/blackout_plots
```

## Addendum: real GNSS recovery and real-trajectory validation

The committed `data/member1_imu_speed.npz` has no position/GPS fields at all. The **official**
IO-VNBD source (https://github.com/onyekpeu/IO-VNBD, branch `master`, git-lfs) does: its
`Synchronised V abd S datasets/Categorised IOVNB Dataset/<driver>/<trip>/S-<trip>.csv` files carry
`GPS LATITUDE/LONGITUDE/ALTITUDE/SPEED/ACCURACY/SATELLITES` alongside the same accelerometer/
gyroscope columns our npz kept. `scripts/recover_iovnbd_gnss.py` downloads (git-lfs, not the tiny
pointer blob) the six test-split trips (S1, S2, S3a, S3b, S3c, S4 -- exactly this repo's held-out
trip families) and cross-correlates each session's real accelerometer column against the npz's to
find the exact row alignment (never assumed -- a session is skipped, not guessed, if the best match
exceeds `ALIGN_MAX_MAE`). All 9 npz session blocks for these 6 trips aligned with MAE 0.02-0.46 m/s^2
and 100% GPS fix coverage; output is `data/derived/gnss_reference.npz` (gitignored, like the raw
data itself -- regenerate via the reproduce command below). `data/member1_imu_speed.npz` was opened
read-only throughout and its mtime/hash are unchanged.

**Real-trajectory blackout validation** (`member5_engine/scripts/real_data_blackout_benchmark.py`):
runs the real M2(10 Hz)->M1(GRU)->M3 chain on REAL recorded IMU from session `S2__s01` (the longest
recovered trip), with an artificial blackout window and REAL recovered GPS as both the aiding signal
(outside blackout) and the ground truth (never fed to the estimator during blackout). Two honest
findings, not glossed over:

1. **This session's real GPS fix rate is far below 10 Hz** (one genuine fix roughly every ~10 s, held
   constant in the log between updates, confirmed by inspection) -- error/distance were computed only
   at genuine fix rows, never on the held-constant values (that would fabricate a false high-rate
   ground truth).
2. **Member 2's calibration is measurably less stable on this real 10 Hz recording than in the
   synthetic 100 Hz benchmark**: `FULLY_ALIGNED` only 24-34% of the time over the session, frequently
   dropping to `REINITIALIZING` (the gravity-tilt-jump guard, `gravity_max_tilt_jump_rad`, firing on
   real per-sample vibration/tilt noise). In the best available ~380 s `FULLY_ALIGNED` stretch found
   in this trip, the real-data blackout result was **50 m: 116%, 1 km: 70%** -- both well over the
   10% SIH bound, unlike the synthetic 100 Hz result.

**This is not a regression of the proven synthetic result and the two must not be conflated.** Real
production Member 2 always runs at 100 Hz (`docs/member5/INTEGRATION.md`); this real IO-VNBD
recording is only available at its native 10 Hz, so `FrameAlignerConfig(sample_rate_hz=10.0)` was
used to drive it honestly at the rate the real data actually has -- but M2's tilt-jump and other
per-sample thresholds were tuned/validated for 100 Hz operation, so this test point exercises M2
partly outside its designed operating regime, on top of exposing it to genuinely noisier real-world
motion than the clean synthetic scenario. The synthetic 100 Hz benchmark (50 m 1.71%, 1 km 3.47%,
1271 m/96 s 0.03%) remains the validated result for the actual production configuration and is
**unchanged and not overwritten** by this real-data finding. The real-data result is reported because
it is real, honest information the SIH team should have, not because it changes what ships: it
identifies a genuine open question (does M2's calibration hold up on real 100 Hz phone data as well
as it does synthetically?) that this repository cannot answer without a real 100 Hz recording, which
does not exist in the available data (IO-VNBD is natively 10 Hz). No further tuning was attempted
against this real-data result in this pass, per instruction.

Reproduce:
```bash
cd member1-ml
# one-time: download the 6 test-split raw files (git-lfs; ~57 MB total) from the official repo, e.g.
#   curl -s -o <dir>/S-S1.csv "https://media.githubusercontent.com/media/onyekpeu/IO-VNBD/master/Synchronised%20V%20abd%20S%20datasets/Categorised%20IOVNB%20Dataset/S%20(Driver%20A)/S1/S-S1.csv"
#   (repeat for S2, S3a, S3b, S3c, S4)
python scripts/recover_iovnbd_gnss.py --raw-dir <dir> --out data/derived/gnss_reference.npz
python ../member5_engine/scripts/real_data_blackout_benchmark.py --session S2__s01 \
    --blackout-start-s 3210 --blackout-duration-s 380
```

## Addendum 2: M2 forensic fix (root cause of the real-10Hz instability)

**Root cause, precisely identified by instrumentation, not guessed:** `FrameAligner::checkPhoneMoved`
(`member2_alignment/python/sih26168_alignment/frame_aligner.py` /
`member2_alignment/cpp/src/FrameAligner.cpp`) fires a **full, destructive re-initialization**
(clears yaw, drops the gravity estimate entirely) the instant a single raw accelerometer sample's
direction deviates more than 0.6 rad from the current "up" estimate while its magnitude stays near
gravity. Instrumenting every REINITIALIZING transition on real session `S2__s01` showed the OTHER
candidate mechanism (the gravity EMA's tilt-jump guard, the target of a previous, reverted attempt)
**never fired at all** -- 100% of the 22 observed resets came from `checkPhoneMoved`. Inspecting the
raw samples around every one of those 22 triggers showed the same signature every time: exactly one
isolated sample with a large horizontal spike (e.g. `[-1.08, 4.32, 6.70]`), with completely normal
samples immediately before and after it -- the signature of a transient road shock/pothole, not a
sustained phone pick-up (which would show elevated deviation over many consecutive samples). This
check has no temporal debounce at all, so a single shock sample is indistinguishable from genuine
handling.

**Fix:** require the deviation condition to persist for a minimum **wall-clock duration**
(`phone_moved_min_duration_s`, default 0.15 s -- not a fixed sample count, so it is correctly
rate-independent) before declaring re-initialization, exactly mirroring the existing debounce pattern
already used elsewhere in this file (`static_streak_s`/`min_static_duration_s`). The 0.6 rad
direction threshold itself, and the `|a| ~ g` magnitude gate, are **unchanged** -- this is not a
threshold-loosening, it is requiring the same threshold to be sustained rather than instantaneous.
Implemented identically in both the Python reference (`frame_aligner.py`, `types.py`) and the C++
mirror (`FrameAligner.cpp`/`.hpp`, `calibration_types.h`) -- the C++ side is unbuilt/unverified like
the rest of this repo's C++ in this sandbox, but is a direct, mechanical port of the same logic.

**Measured effect (full `S2__s01` session, apples-to-apples, before/after isolated by `git stash`):**

| Metric | Before | After |
|---|---:|---:|
| `FULLY_ALIGNED` | 26.0% | **37.2%** |
| `REINITIALIZING` | 57.4% | **31.4%** |

A genuine, substantial, reproducible improvement -- not cherry-picked (measured on the exact same
full session both times, with the same GNSS-aiding schedule). It did **not**, however, flip most
individual real-trip 50 m/1 km blackout checkpoints from FAIL to PASS (see the main report) -- the
underlying real data still has other real-world characteristics (genuinely sparse real GPS fixes,
low real speeds, and remaining calibration episodes from causes other than this one) that a single
targeted fix does not resolve. The 100 Hz M2 test suite (adversarial/pothole/static/vibration, 71
tests) and the controlled 100 Hz blackout benchmark (1.71%/3.47%/0.03%) are both **unchanged** by
this fix, confirmed by direct re-run.
