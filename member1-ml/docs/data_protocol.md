# Data protocol — Member 1 (IMU-only vehicle speed)

## Dataset structure

File: `data/member1_imu_speed.npz` (untracked, read-only). It is a flat table with one row per
10 Hz sample, and rows are grouped into contiguous session blocks. All numbers below were
checked with `python -m src.data.inspect_dataset`.

| Key | Shape | Dtype | Role |
|---|---|---|---|
| `acc` | (817681, 3) | float32 | **model input**: accelerometer XYZ |
| `gyr` | (817681, 3) | float32 | **model input**: gyroscope XYZ |
| `target_speed_mps` | (817681,) | float32 | **target**: vehicle speed in m/s (range 0 – 36.63) |
| `t_session_s` | (817681,) | float32 | seconds since session start, used only for continuity checks |
| `session_id` | (817681,) | <U10 | grouping, e.g. `Vw4__s00` (34 unique) |
| `trip_id` | (817681,) | <U5 | grouping, e.g. `Vw4` (28 unique) |
| `sample_idx` | (817681,) | int64 | per-session counter, used only for continuity checks |
| `verdict` | (817681,) | <U4 | per-session quality tag `GOOD` / `OK`, metadata only |

Findings:
- `acc`, `gyr`, `t_session_s` and `sample_idx` contain no NaN or Inf values.
- `target_speed_mps` has 14 NaN values. Each one is the **last row** of a session. Windows that end on those rows are rejected.
- Every session is one contiguous block, `sample_idx` increases by exactly 1, and dt stays within [0.0996, 0.1006] s. The sampling rate is 10 Hz, and no session has an internal break.
- The file has no vehicle-side, GPS or magnetometer fields, and **no explicit vehicle identifier**.
- The target is already in m/s. If a future file stores km/h, set `data.target_units: km/h`, and `load_npz` divides by 3.6 when loading.

## Allowed model inputs

Only `acc` and `gyr` are allowed. They are stacked into `(N, 6)` in the order
`[acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z]`.

This rule is enforced in code, not just by convention. `src/data/dataset.py::build_model_input` is the only
place where model inputs are assembled, and it calls `check_input_keys`. That check raises `LeakageError` for
any key outside `("acc", "gyr")`, and for any key matching a forbidden pattern.

## Forbidden inputs (never passed to a model)

- `veh_*` fields, vehicle speed, wheel speeds, vehicle yaw rate, vehicle heading, indicated speed
- Phone GPS latitude, longitude, speed, accuracy and orientation/bearing
- Magnetometer data
- `trip_id` and `session_id`, `verdict`, `sample_idx`, and any date or time field (including `t_session_s`)
- `has_ground_truth`, `gps_outage`
- The target itself, and any future sample (see windowing)

`tests/test_data.py` checks each of these names against the leakage guard. It also checks that extra fields added to the
arrays never reach the IMU matrix.

## Target

`target_speed_mps` is the speed at the **last sample of each window** (the prediction point), in m/s.
It is used only as the supervised label. All metrics are reported in m/s, with km/h copies (×3.6).

## Windowing (`src/data/windowing.py`)

- Sampling rate is 10 Hz. Window lengths are 2 s = **20** samples and 4 s = **40** samples.
- A window ending at row `e` covers rows `[e-T+1, e]` and is labelled with `target[e]`. It is **causal**, with no lookahead.
- Stride is **5** for training and **1** for validation and test. Within each session, window ends fall at positions `T-1, T-1+stride, …`.
- A window is **rejected** (never shifted) if any of these is true:
  - it crosses a session boundary
  - `sample_idx` does not increase by 1 between rows
  - |dt − 0.1 s| > 0.02 s
  - any IMU value is non-finite
  - the target at the prediction point is non-finite
- Windows are represented by `int64` end indices. `gather_windows` turns them into `float32 [B, T, 6]`, and
  `iter_window_chunks` does the same in chunks, so stride-1 evaluation doesn't hold every window in memory.
- `assert_windows_valid` re-checks single-session membership, contiguity and label finiteness independently.

## Splits (`src/data/splits.py`)

Splits are assigned per `trip_id`, using full-match regex rules in `configs/member1.yaml`. Rows and windows are never split randomly.

| Split | Rule | Trips in current NPZ | Sessions | Rows |
|---|---|---|---|---|
| train | `Vw\d+[a-z]?`, `Vfa02` | Vfa02, Vw2, Vw3, Vw4, Vw5, Vw6, Vw9, Vw10, Vw11, Vw12, Vw13, Vw14a, Vw14b, Vw14c, Vw16a, Vw16b, Vw17 (17) | 17 | 305,570 |
| val | `M` | M | 2 | 105,715 |
| test | `S\d+[a-z]?` | S1, S2, S3a, S3b, S3c, S4 | 9 | 301,757 |
| *excluded* | no rule matches | Vfa01, Vta1a, Vta1b, Y1 | 6 | 104,639 |

`make_split` calls `assert_no_group_leakage`. That check fails if two splits share a row, `session_id`, `trip_id`,
or **trip family** (the alphabetic prefix of `trip_id`: `M`, `S`, `Vfa`, `Vta`, `Vw`, `Y`).

The trips `Vfa01`, `Vta1a`, `Vta1b` and `Y1` fall outside the agreed split, so they are left out of the fixed split rather than
assigned arbitrarily. Note that `Vfa01` shares a family with the training trip `Vfa02`.

### Leave-one-vehicle-out

The NPZ has no vehicle ID, so `lovo_folds(trip_id, level)` holds out one **group** per fold:
- `level: family` (the default) holds out a whole trip family. This is the conservative stand-in for a vehicle.
- `level: trip` holds out a single trip.

Milestone 1 only provides this as scaffolding. No LOVO results have been produced yet.

## Augmentation (`src/data/augmentation.py`)

Every window gets one rotation matrix `R` (det = +1), applied to acc and gyr at every time step of
that window (matching a rigid change of phone mounting), never to the target. `probability` sets the
fraction of windows that get rotated (the rest keep the identity), and rotation is seeded through
`np.random.Generator`.

Four policies (`training.augmentation_policy`), compared in Milestone 3 (`docs/experiments.md`):

| Policy | Rotation | Applied at eval/inference too? |
|---|---|---|
| `none` | none | -- |
| `so3` (Milestone 2 default) | full random SO(3): random axis, `max_angle_deg >= 180` samples uniformly over SO(3) via random unit quaternions, else a random axis with angle uniform in `[0, max]` | no |
| `yaw` (**chosen**, Milestone 3) | random rotation about the vertical (gravity) axis only | no |
| `gravity_yaw` | the window's estimated gravity direction (its mean acc vector) rotated to `+z`, THEN a random yaw rotation | **yes** -- the gravity-alignment part is deterministic and must be applied identically to validation, test and inference windows, not just training |

`yaw` was chosen over `so3` (this dataset's one fixed mounting tilt makes full SO(3) invariance a
harder ask than the benchmark rewards) and over `none` (zero rotation robustness is not
deployment-safe) and over `gravity_yaw` (its own noisy per-window gravity re-estimate turned out to
hurt more than it helped, on this already well-aligned dataset) -- see `docs/experiments.md` for the
actual measured comparison.

## Normalization (neural models)

`fit_normalization`, in `src/models/tcn_velocity.py`, takes training-split IMU rows and training window labels only. It computes:
- one input scale per sensor
- the target mean and std

These are stored as buffers in the model and reused unchanged for validation, test and inference. Validation data is used
only for per-epoch monitoring, early stopping and picking the best checkpoint.

## Reproducibility

- Settings come only from `configs/member1.yaml`, including the seed (`seed: 42`), which drives the augmentation RNG.
- Ridge regression and the physics baseline are deterministic.
- Neural training calls `seed_everything`, which seeds Python, NumPy and torch, turns on deterministic algorithms and sets cuDNN to deterministic with `CUBLAS_WORKSPACE_CONFIG`. It also uses a seeded shuffle generator and per-epoch augmentation RNGs seeded from `(seed, epoch)`. Rerunning on the same machine gave identical metrics.
- There are no manual steps. The data file is only read, never written.

## Milestone 4 audit

A full leakage/causality re-audit of this protocol (allowed inputs, splits, windowing, normalization,
augmentation) against the actual code was carried out as part of Milestone 4 (inference, ONNX export,
edge benchmark) and found every safeguard on this page already correctly enforced in code, not just
documented -- see `docs/experiments.md`'s "Final leakage / causality audit" section for what was
specifically checked and why no changes were needed.
