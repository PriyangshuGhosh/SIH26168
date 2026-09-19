# Cooperative localization mathematics

**IMPLEMENTED** (host). **SIMULATED** observations. Not a GNSS replacement.

## When does a remote vehicle help *our* position?

A remote absolute GNSS report does **not** observe ego position by itself. There is no ranging radio in MODE A.

Defensible path used here:

1. While **our GNSS is available**, snapshot  
   `r = p_remote_broadcast - p_ego_gnss`  
   (GNSS-era estimates, not current dead-reckoning treated as independent truth).
2. During **our GNSS outage**, propagate `r` with relative velocity  
   `r_pred = r + (v_remote - v_ego) Δt`  
   then  
   `p_ego_meas = p_remote_now - r_pred`.
3. Covariance: remote `σ²` × age scale × quality + snapshot cov + `(σ_rel Δt)²` + time-sync `σ_t |v|`.
4. While GNSS is on, cooperative **position is correlated** → `Unavailable` / `correlated_with_gnss` (no double-counting).

If no snapshot exists, or every snapshot is older than `relative_snapshot_max_age_s` (default **30 s**), V2X **cannot** help: `no_observable_relative`.

More remotes are not automatically better. North outliers more than 40 m from the median are dropped when there are ≥3 candidates; **east outliers are not median-gated**. NIS is computed on the **fused** mix, not by permanently excluding a spoofed track. Inverse-variance fusion treats candidate covariances as **independent**; they are not, because every `r` shares the same GNSS-era ego snapshot. That **understates** fused `R` in principle. As `Δt` grows, process noise inflates `R` and a biased mix can later fall inside the χ² gate (Accept ≤ 5.991, Downweight ≤ 9.210). That is a **SIMULATED** limitation of this estimator, not a claim that extra vehicles always help.

Explicit relative range (`has_explicit_relative`) is supported in the message model for a future radio; the default simulator does **not** provide ranging.

Gating: 2-DOF χ² NIS, Accept ≤ 5.991, Downweight ≤ 9.210, else Reject. Same family as Member 3 GNSS NIS. No fake `confidence = 0.9`.

**NOT VALIDATED:** Android, real V2X, C-V2X, NR-V2X, Member 3 end-to-end, real driving.
