# Member 4 HMM equations

## Emission (log domain)

\[
\log p_{\mathrm{emis}}(z_t \mid c) =
-\frac12\left(\frac{d_\perp(z_t,c)}{\sigma_p}\right)^2
+ w_\psi\left[
-\frac12\left(\frac{\Delta\psi(z_t,c)}{\sigma_\psi}\right)^2 - R(c)
\right]
\]

- \(d_\perp\): perpendicular distance (m) from observation to candidate polyline.
- \(\sigma_p\): position uncertainty from Member 3 covariance
  \(\sigma_p = \sqrt{\max(P_{nn}, P_{ee})}\).
- \(\Delta\psi\): smallest heading error vs road heading (or reverse).
- \(R(c)\): reverse-travel penalty when reverse heading fits better.
- If heading is invalid, \(w_\psi = 0\) (graceful degradation).

Large \(\sigma_p\) flattens emissions — matching must not invent precise position.

## Transition (log domain)

\[
\log p_{\mathrm{trans}}(c_{t-1}\!\to\!c_t) =
-\frac12\left(\frac{d_{\mathrm{net}}-d_{\mathrm{obs}}}{\sigma_t}\right)^2
+ 0.25\left[
-\frac12\left(\frac{\Delta\psi_{\mathrm{road}}-\Delta\psi_{\mathrm{yaw}}}{\sigma_\Delta}\right)^2
\right]
\]

Disconnected network paths score \(-\infty\) (hard prune).

## Decoding

Sliding-window Viterbi over the last \(W\) observations (default \(W=8\)).
Batch `matchTrajectory` runs full-sequence Viterbi. This is **not** independent
nearest-road snapping.

## Confidence / on-road

\[
\mathrm{confidence}(c^\*) = \mathrm{softmax}_{c\in C_t}\big(\log p_{\mathrm{emis}}(z_t\mid c)\big)_{c^\*}
\]

Softened by large \(\sigma_p\). `is_on_road_network` requires confidence, distance,
and uncertainty gates. Failures pass through raw lat/lon with low confidence.
