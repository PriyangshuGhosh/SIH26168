# Member 2 — Algorithm

## Selected approach: hybrid gravity tilt + motion-constrained yaw

Streaming pipeline:

```text
Raw IMU (100 Hz)
    → validate sample
    → quasi-static detector
    → gravity / roll-pitch estimator
    → (optional) GNSS speed-rate aid
    → longitudinal-axis PCA + sign resolver
    → confidence / status
    → R_vp, q_pv, aligned vectors
```

This is **not** an AHRS that claims world heading. It estimates **phone-to-vehicle**
mounting. Downstream EKF (Member 3) owns navigation heading.

## Approaches considered

| ID | Approach | Verdict |
|---|---|---|
| A | Static gravity alignment | **Necessary** for roll/pitch. **Insufficient** for yaw. |
| B | PCA of acceleration | Useful for the *longitudinal axis* after gravity removal. Alone, 180° ambiguous and poisoned by potholes/turns. |
| C | Gyro integration | Tracks *changes* in orientation; does not observe mount yaw; drifts. Used only as a motion/phone-handling cue. |
| D | Vehicle-motion constrained heading | **Adopted** for yaw: require straight, non-shock, sufficiently strong horizontal specific force; optional GNSS `dv/dt` for sign; optional turn `ω_z` vs lateral accel to resolve 180°. |
| E | Mahony/Madgwick/EKF AHRS | Estimates attitude vs gravity (and magnetometer). Magnetometer is hostile in cars; AHRS still does **not** give chassis yaw. Rejected as the primary mount solver. Extra cost, extra failure modes. |
| F | **Hybrid (selected)** | A + D with gated PCA, optional GNSS-as-aid, conservative status. Cheap, observable, EKF-friendly. |

### Observability notes

- Stationary / weak accel: roll/pitch only (`YAW_UNCERTAIN` or `ROLL_PITCH_VALID`).
- Braking vs throttle: same axis, opposite sign — GNSS `dv/dt` or turn consistency required to lock sign; otherwise yaw stays uncertain.
- Turns: centripetal acceleration is **lateral**, not forward. Turns are not used to invent a forward axis.
- Potholes: rejected by shock `|a|` gate.
- Phone movement: gravity-up jump while `|a|≈g` triggers `REINITIALIZING`.
- GNSS absence: fully supported (degraded yaw). GNSS is never a runtime dependency.

## Quasi-static detector

A window of `static_window_samples` (default 0.5 s at 100 Hz) is quasi-static only if
**all** hold:

1. `||a| − g| < static_accel_norm_tol` for every sample (not `|a|≈g` on a single sample).
   Longitudinal 1–2 m/s² still leaves `|a|` near `g`; a tight tolerance plus (4) is required.
2. `max |ω| < static_gyro_norm_max`.
3. Per-axis acceleration variance `< static_accel_var_max`.
4. If gravity is already known, the window-mean direction must lie within
   `static_dir_align_rad` of `g_up_p` (rejects accel/braking masquerading as gravity).
5. Window duration and a minimum static streak (`min_static_duration_s`).

## Gravity / roll / pitch

During quasi-static intervals, specific force is EMA-smoothed and normalized to
`g_up_p`. `R_gp = rotationGravityUpToVehicleZ(g_up_p)` satisfies `R_gp g_up_p = [0,0,1]`.
The remaining yaw about Z is **not** vehicle heading.

## Yaw estimator

After levelling, `a_h = (R_gp a_p)_{xy}` is linear-ish horizontal specific force
(gravity sits on Z). Evidence is accepted only if:

- not a shock (`|a| < yaw_shock_accel_max`);
- approximately straight (`|ω| < yaw_max_gyro_norm`);
- `|a_h| ≥ yaw_min_horiz_accel`.

A 2×2 scatter matrix of `a_h` is accumulated. The principal eigenvector is the
longitudinal **axis**. Sign:

1. Optional GNSS: if HDOP/sats/age pass, `sign(dv/dt)` tags whether `a_h` is forward or brake.
2. Else, if enough turn samples exist, `sign(ω_z) * a_lat` consistency (vehicle: `a_y ≈ ω_z v_x` with `v_x≥0`).
3. Else: **do not guess**. Status `YAW_UNCERTAIN`. Output uses tilt-only `R_gp`.

When yaw is locked: `R_vp = R_z(ψ) R_gp` with `ψ = −atan2(u_y, u_x)` for signed axis `u`.

## Online processing

`FrameAligner::process` is causal, deterministic, and uses fixed-size circular
buffers (`kMaxWindow = 256`). No per-sample heap allocation in C++. Not internally
thread-safe: serialize calls (Member 5 may mutex). `reset()` clears all state.

Gaps `> gap_reset_s` flush the static window and may mark `DEGRADED` without
inventing a new yaw.

## Configuration

All thresholds live in `FrameAlignerConfig` / `sih26168_alignment.types.FrameAlignerConfig`.
Do not scatter magic numbers in the hot path.
