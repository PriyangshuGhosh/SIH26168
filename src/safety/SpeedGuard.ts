// Centralized speed conversion + validation
// Every km/h displayed in the UI must pass through this guard to catch
// NaN / Infinity / negative / absurd values (e.g. 194.4 m/s ≈ 700 km/h regression).

import { RejectionReason, SpeedEvaluation } from "../types";

export const ABSURD_SPEED_MPS = 55.0; // ~198 km/h passenger road safety ceiling (matches Member 5 SpeedValidityConfig)
export const MPS_TO_KMH = 3.6;

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

export function formatKmh(mps: number | null | undefined): string {
  const evalRes = evaluateSpeed(mps);
  if (!evalRes.valid || evalRes.kmh === null) return "--";
  return evalRes.kmh.toFixed(1);
}

export function rejectionLabel(reason: RejectionReason): string {
  switch (reason) {
    case RejectionReason.ABSURD_SPEED:
      return "ABSURD SPEED (>360 km/h REJECTED)";
    case RejectionReason.NAN_SPEED:
      return "INVALID NUMERIC SPEED (NaN)";
    case RejectionReason.INF_SPEED:
      return "INFINITE SPEED VALUE";
    case RejectionReason.NEGATIVE_SPEED:
      return "NEGATIVE SPEED VALUE";
    case RejectionReason.STALE_SAMPLE:
      return "STALE SENSOR DATA";
    case RejectionReason.TIMESTAMP_REGRESSION:
      return "TIMESTAMP REGRESSION DETECTED";
    case RejectionReason.NAN_POSITION:
      return "INVALID GNSS COORDINATES";
    case RejectionReason.ENGINE_FAULT:
      return "HARDWARE/ENGINE FAULT";
    default:
      return "SPEED UNAVAILABLE";
  }
}
