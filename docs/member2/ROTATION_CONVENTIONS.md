# Member 2 — Rotation and Frame Conventions

**Gravity determines roll and pitch. Gravity does not determine absolute yaw.**

## Frames

| Frame | Symbol | Definition |
|---|---|---|
| Phone IMU | `p` | Native right-handed IMU axes. Arbitrary vs. the chassis. |
| Vehicle | `v` | Right-handed. **+X forward, +Y left, +Z up.** |
| Gravity-levelled phone | `g` | Intermediate frame with +Z along estimated specific-force “up”. Yaw about Z is a canonical gauge, *not* vehicle heading, until yaw is observed. |

Both frames are right-handed. Vectors are 3×1 columns. Rotation matrices act on the left.

## Mapping

```text
a_v     = R_vp * a_p
omega_v = R_vp * omega_p
```

`R_vp` is the DCM **phone → vehicle** (change of coordinates of the same physical
vector). Inverse: `R_pv = R_vp^T`.

## Quaternion `q_pv`

- Hamilton product, stored as **`[w, x, y, z]`**.
- `q_pv` **rotates a vector from the phone frame into the vehicle frame**:

```text
v_v = q_pv ⊗ [0, v_p] ⊗ q_pv*
```

- Equivalent: `v_v = R_vp v_p` with `R_vp = rotation_matrix_from_quat(q_pv)`.
- Inverse / vehicle→phone: `q_vp = q_pv*` (conjugate).
- `w` is forced ≥ 0 after normalization to remove the q/−q double cover in outputs.
- Composition: `q_ac = q_ab ⊗ q_bc` (apply `q_bc` first), matching `R_ac = R_ab R_bc`.
- Active vs passive: we treat `R_vp` as a **passive** coordinate representation
  change. This matches “express the IMU vector in vehicle axes”.

Named helpers (Python and C++):

- `phoneToVehicleVector()`
- `vehicleToPhoneVector()`
- `quatPhoneToVehicle()`
- `rotationMatrixPhoneToVehicle()` / `rotationGravityUpToVehicleZ()` then `Rz(yaw)`

## Accelerometer / gravity

The IMU reports **specific force** `f = a_lin − g`.
With `g_v = [0, 0, −g]` (Z up), a stationary vehicle reads `f_v ≈ [0, 0, +g]`.
Quasi-static accelerometer averages therefore estimate the **up** direction in the
phone, which fixes roll and pitch relative to vehicle Z — **not** yaw about Z.

## Yaw

Yaw is the remaining rotation about vehicle/levelled Z. It is observable only when
a unique **longitudinal** axis can be inferred (sustained forward/brake specific
force, with optional GNSS `dv/dt` for sign **only when |a_h| agrees with |dv/dt|**,
and optional turn consistency to resolve 180°). Potholes, vibration, lane changes,
and generic gyro energy are not heading. GNSS course is unused.

## Units and time

| Quantity | Unit |
|---|---|
| timestamp | seconds (monotonic or Unix; only differences used) |
| accelerometer | m/s² specific force |
| gyroscope | rad/s |
| GNSS speed (optional) | m/s |
| GNSS HDOP | dimensionless |
| quaternion | unitless, `[w,x,y,z]` |

Nominal rate: **100 Hz**. `dt` is taken from timestamps, not assumed exact.

## Assumptions (explicit)

1. Phone and vehicle are rigid during a valid calibration interval.
2. Vehicle +Z is “up” in the same sense as gravity (no large sustained bank).
3. Longitudinal specific force dominates lateral during the evidence windows used for yaw.
4. Optional GNSS is **calibration evidence only**; the hot path never requires it.
5. After a time gap > `gap_reset_s`, static windows are cleared and status may drop to `DEGRADED`.
6. Duplicate timestamps (`dt < min_dt_s`) do not update estimators.
7. Timestamp reversal yields `INVALID` and does not mutate calibration state.
8. NaN/Inf/unreasonable magnitudes yield `INVALID` and do not mutate estimators.
