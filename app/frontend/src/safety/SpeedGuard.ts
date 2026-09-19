// Centralized speed conversion + validation.
// Every km/h shown in the UI MUST come through here so a single guard
// catches NaN / Infinity / negative / absurd values (e.g., the historical
// 194.4 m/s ≈ 700 km/h regression).
//
// This intentionally does NOT clamp. Upstream (Member 1/3/5) must reject
// impossible measurements; Member 6 refuses to display them, surfacing
// "Speed unavailable" instead.

import { RejectionReason } from "../navigation/types";

// Physical ceiling for a road vehicle in this app's context (m/s).
// 100 m/s ≈ 360 km/h. Anything above this is treated as garbage rather
// than clamped, so the fault is visible instead of hidden.
export const ABSURD_SPEED_MPS = 100;

export const MPS_TO_KMH = 3.6;

export interface SpeedEvaluation {
  valid: boolean;
  reason: RejectionReason;
  kmh: number | null;
}

export function evaluateSpeed(mps: number | null | undefined): SpeedEvaluation {
  if (mps === null || mps === undefined) {
    return { valid: false, reason: RejectionReason.NONE, kmh: null };
  }
  if (Number.isNaN(mps)) {
    return { valid: false, reason: RejectionReason.NAN_SPEED, kmh: null };
  }
  if (!Number.isFinite(mps)) {
    return { valid: false, reason: RejectionReason.INF_SPEED, kmh: null };
  }
  if (mps < 0) {
    return { valid: false, reason: RejectionReason.NEGATIVE_SPEED, kmh: null };
  }
  if (mps > ABSURD_SPEED_MPS) {
    return { valid: false, reason: RejectionReason.ABSURD_SPEED, kmh: null };
  }
  return { valid: true, reason: RejectionReason.NONE, kmh: mps * MPS_TO_KMH };
}

// UI helper — either the formatted km/h string or null when invalid.
export function formatKmh(mps: number | null | undefined): string {
  const evalRes = evaluateSpeed(mps);
  if (!evalRes.valid || evalRes.kmh === null) return "--";
  return evalRes.kmh.toFixed(1);
}
