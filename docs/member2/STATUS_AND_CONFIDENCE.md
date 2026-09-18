# Member 2 — Status machine and confidence

## `CalibrationStatus`

| Value | Name | Meaning for downstream |
|---|---|---|
| 0 | `UNINITIALIZED` | No usable tilt yet. `R_vp = I`. **Do not treat axes as vehicle.** |
| 1 | `STATIC_DETECTED` | Quasi-static window seen; gravity not yet committed. |
| 2 | `ROLL_PITCH_VALID` | Tilt known. X/Y are **not** necessarily forward/left. Gravity on Z is usable. |
| 3 | `YAW_UNCERTAIN` | Longitudinal *axis* may exist but **sign/yaw not locked**. Do not use `v_x` from `a_x` as vehicle forward. |
| 4 | `FULLY_ALIGNED` | Tilt + signed yaw locked with supporting evidence. Vehicle axes intended. |
| 5 | `DEGRADED` | Previously useful alignment, now stale/gapped/inconsistent. Last `R_vp` may still be applied; trust is reduced. |
| 6 | `REINITIALIZING` | Phone likely moved/remounted. Yaw cleared; gravity being re-acquired. |
| 7 | `INVALID` | This sample failed validation (NaN/Inf/time/magnitude). Estimators were **not** updated. |

```text
UNINITIALIZED → STATIC_DETECTED → ROLL_PITCH_VALID ┬→ YAW_UNCERTAIN → FULLY_ALIGNED
                                                   │         ↑              │
                                                   │         └──────────────┤
                                                   └→ REINITIALIZING ───────┘
Any validated path may emit INVALID for a bad sample without resetting history.
Gaps / inconsistency → DEGRADED.
```

## Confidence (not a fake probability)

`CalibrationConfidence` terms are in `[0, 1]`:

| Field | Meaning |
|---|---|
| `gravity` | Stability of the estimated up-vector (small angular jumps while static raise it). |
| `yaw_observability` | Strength of unique longitudinal axis **and** resolved sign (PCA evidence, GNSS `dv/dt`, turn consistency). |
| `temporal` | Recency of gravity and yaw evidence (decays when evidence is old). |
| `sensor_quality` | Fraction of recent samples that passed validation. |
| `overall` | Documented weighted mix of the above, **capped** by status so yaw-unknown never looks “fully confident”. |

Weights (must stay in sync with code):

- `FULLY_ALIGNED`: `0.30 g + 0.45 yaw + 0.15 temporal + 0.10 sensor`, and **status is
  withheld unless `overall ≥ fully_aligned_min_confidence` (default 0.62)**.
- `YAW_UNCERTAIN`: `min(0.55, 0.70 g + 0.10 yaw + 0.10 temporal + 0.10 sensor)`
- `ROLL_PITCH_VALID` / `DEGRADED`: `min(0.50, 0.75 g + …)`
- `UNINITIALIZED`: `overall = 0`
- `INVALID` sample: `overall ≤ 0.05`

Yaw is revoked to `YAW_UNCERTAIN` when evidence is stale (`> 2 · yaw_hold_s`) or a new
signed axis disagrees by more than `yaw_disagree_rad`. Vehicle X is then **not** applied
(`R_vp` falls back to tilt-only).

**How Members 1/3/5 should use it**

- Trust vehicle-frame **X as forward** only if `status == FULLY_ALIGNED` and `overall` is acceptable to them (Member 2 does not impose a single project-wide cutoff beyond `fully_aligned_min_confidence` used internally).
- `ROLL_PITCH_VALID` / `YAW_UNCERTAIN`: Z (gravity) is the only axis that should be treated as physically meaningful.
- `INVALID`: ignore the sample or hold last good aligned vector; do not update EKF with this IMU tick.
- Never interpret `overall` as “probability the mount is correct”.
