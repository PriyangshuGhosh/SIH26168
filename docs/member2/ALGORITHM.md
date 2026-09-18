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
   Longitudinal 1–2 m/s² still leaves `|a|` near `g`; a tight tolerance plus (4)–(5) is required.
2. `max |ω| < static_gyro_norm_max`.
3. Per-axis acceleration variance `< static_accel_var_max`.
4. If gravity is already known, **every sample** in the window (not only the mean) must lie
   within `static_dir_align_rad` of `g_up_p`. Mean-only gating allowed the first accel samples
   to poison the gravity EMA; once `g_up_p` tracks specific force, later `|a|≈g` checks pass
   and yaw evidence disappears.
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

If quality GNSS is present **and** speed ≥ `gnss_min_speed_mps`, a sample is accumulated
into the PCA scatter **only when** `|a_h|` and `|dv/dt|` agree (`max ≤ min · (1+rel)` **and**
`max−min ≤ gnss_imu_agree_abs`), `|dv/dt|` is in `[gnss_min_accel, gnss_max_abs_accel]`,
and the GNSS fix is fresh (HDOP/sats/age).
A lateral lane-change pulse with a slow/unrelated speed ramp therefore does **not**
build a “longitudinal” axis. Spiked `dv/dt` is ignored (not blended into the GNSS accel EMA).

A 2×2 scatter matrix of accepted `a_h` is accumulated. The principal eigenvector is the
candidate longitudinal **axis**, not a direction. It is rejected unless the eigenvalue
ratio `λ_max/λ_min ≥ yaw_pca_ratio_min` (default 2.2). Equal-ish eigenvalues mean the
horizontal force is not directional (turns + accel, lane change + throttle, vibration):
status stays `YAW_UNCERTAIN`. Eigenvector sign is arbitrary; ±180° is resolved separately.

Sign:

1. Optional GNSS: if GNSS–IMU magnitudes agree as above, `sign(dv/dt)` tags whether `a_h`
   is forward or brake. Evidence integral must reach `gnss_sign_evidence_min`.
2. Else, if enough turn samples exist, `sign(ω_z) * a_lat` consistency (vehicle:
   `a_y ≈ ω_z v_x` with **`v_x≥0` assumed**).
3. If **both** GNSS and turn signs are available and they **disagree**, yaw is revoked
   (`YAW_UNCERTAIN`). Reverse + unsigned GNSS speed is the usual cause.
4. Else: **do not guess**. Status `YAW_UNCERTAIN`. Output uses tilt-only `R_gp`.

When yaw is locked: `R_vp = R_z(ψ) R_gp` with `ψ = −atan2(u_y, u_x)` for signed axis `u`.
If a later lock disagrees by more than `yaw_disagree_rad`, yaw is revoked.
Yaw older than `2 · yaw_hold_s` without new evidence is revoked (`YAW_UNCERTAIN`).

`FULLY_ALIGNED` is emitted only if signed yaw is locked **and** `overall ≥ fully_aligned_min_confidence`
(default 0.62). Low overall never advertises a usable chassis X.

### Known limitations (not silently “solved”)

- GNSS `dv/dt` cannot see lateral vs longitudinal. A **matched-magnitude** speed-up coinciding
  with a nearly straight lateral-only IMU pulse can still look like forward accel. Honest
  GNSS + simultaneous lateral and longitudinal of similar size usually fails the PCA ratio
  gate (near-equal eigenvalues) and stays uncertain.
- Systematically inverted GNSS speed (always decreasing while the car accelerates) can still
  produce a **180°** sign error if magnitudes agree. Course is accepted on the wire but **not**
  used (hostile in urban canyons).
- Reverse (`v_x < 0`) is **not observable** vs a 180° mount when GNSS speed is unsigned:
  reverse accel increases speed and the turn identity `a_y ≈ ω_z v_x` with `v_x≥0` **confirms
  the wrong sign**. Do not treat `FULLY_ALIGNED` during reverse as trustworthy. Signed velocity
  or a known-forward interval is required to fix this; Member 2 does not invent it.
- Phone rotated during strong motion may not look like `|a|≈g` remount; yaw can go stale
  rather than instantly `REINITIALIZING`.
- Android runtime is **NOT VALIDATED**.

## Online processing

`FrameAligner::process` is causal, deterministic, and uses fixed-size circular
buffers (`kMaxWindow = 256`). No per-sample heap allocation in C++. Not internally
thread-safe: serialize calls (Member 5 may mutex). `reset()` clears all state.

Gaps `> gap_reset_s` flush the static window and may mark `DEGRADED` without
inventing a new yaw.

## Configuration

All thresholds live in `FrameAlignerConfig` / `sih26168_alignment.types.FrameAlignerConfig`.
Do not scatter magic numbers in the hot path.
