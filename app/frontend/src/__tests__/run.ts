// Simple hand-rolled runner — no Jest configured on this Expo project.
// Run with: `node -r ts-node/register src/__tests__/run.ts` or via a node
// script that transpiles TS. Also exercised in CI later.

import {
  evaluateSpeed,
  ABSURD_SPEED_MPS,
  MPS_TO_KMH,
} from "../safety/SpeedGuard";
import { RejectionReason } from "../navigation/types";
import { selectRegion, BUILTIN_REGIONS } from "../maps/RegionSelector";
import { SensorPipeline } from "../sensors/SensorPipeline";

let PASS = 0;
let FAIL = 0;
function t(name: string, fn: () => void) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    PASS++;
  } catch (e: any) {
    console.log(`  ✗ ${name}\n    ${e?.message ?? e}`);
    FAIL++;
  }
}
function eq(a: any, b: any) {
  if (a !== b) throw new Error(`expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}
function truthy(v: any, msg = "expected truthy") {
  if (!v) throw new Error(msg);
}
function approxEq(a: number, b: number, tol = 1e-6) {
  if (Math.abs(a - b) > tol) throw new Error(`expected ~${b}, got ${a}`);
}

// -------- SpeedGuard --------
console.log("SpeedGuard");
t("valid 30 m/s → 108 km/h", () => {
  const r = evaluateSpeed(30);
  truthy(r.valid);
  approxEq(r.kmh!, 108, 1e-6);
});
t("null → not valid", () => {
  eq(evaluateSpeed(null).valid, false);
});
t("NaN → NAN_SPEED", () => {
  eq(evaluateSpeed(Number.NaN).reason, RejectionReason.NAN_SPEED);
});
t("Infinity → INF_SPEED", () => {
  eq(evaluateSpeed(Number.POSITIVE_INFINITY).reason, RejectionReason.INF_SPEED);
});
t("negative → NEGATIVE_SPEED", () => {
  eq(evaluateSpeed(-1).reason, RejectionReason.NEGATIVE_SPEED);
});
t("194.4 m/s (700 km/h) → ABSURD_SPEED (never displayed)", () => {
  const r = evaluateSpeed(194.4);
  eq(r.valid, false);
  eq(r.reason, RejectionReason.ABSURD_SPEED);
  eq(r.kmh, null);
});
t("MPS_TO_KMH constant is 3.6", () => approxEq(MPS_TO_KMH, 3.6));
t("boundary at ABSURD_SPEED_MPS is still valid", () => {
  truthy(evaluateSpeed(ABSURD_SPEED_MPS).valid);
});
t("just above ABSURD_SPEED_MPS is rejected", () => {
  eq(evaluateSpeed(ABSURD_SPEED_MPS + 0.001).valid, false);
});
// Normal driving speeds
[0, 1, 5, 10, 30, 50].forEach((v) =>
  t(`normal ${v} m/s is valid`, () => truthy(evaluateSpeed(v).valid)),
);

// -------- RegionSelector --------
console.log("\nRegionSelector");
t("Bengaluru center picks bengaluru", () => {
  const s = selectRegion(12.9716, 77.5946, BUILTIN_REGIONS, null);
  eq(s.active?.regionId, "in-bengaluru");
  eq(s.outOfCoverage, false);
});
t("Vizag center picks vizag", () => {
  const s = selectRegion(17.72, 83.30, BUILTIN_REGIONS, null);
  eq(s.active?.regionId, "in-vizag");
});
t("Mid-Pacific → out-of-coverage, active null", () => {
  const s = selectRegion(0, -150, BUILTIN_REGIONS, null);
  eq(s.outOfCoverage, true);
  eq(s.active, null);
});
t("Active region cached when still inside", () => {
  const active = BUILTIN_REGIONS.find((r) => r.regionId === "in-bengaluru")!;
  const s = selectRegion(12.95, 77.60, BUILTIN_REGIONS, active);
  eq(s.active, active);
});
t("NaN lat → out-of-coverage", () => {
  eq(selectRegion(Number.NaN, 77, BUILTIN_REGIONS, null).outOfCoverage, true);
});

// -------- SensorPipeline --------
console.log("\nSensorPipeline");
t("timestamp regression is dropped", () => {
  const p = new SensorPipeline();
  let emitted = 0;
  p.onSample(() => emitted++);
  p.pushAccel(1_000_000, 0, 0, 9.81);
  p.pushGyro(1_000_000, 0, 0, 0);
  p.pushGyro(500_000, 0, 0, 0); // regression
  eq(emitted, 1);
  truthy(p.getStats().droppedRegression >= 1);
});
t("stale accel (> STALE_MS after gyro) is dropped", () => {
  const p = new SensorPipeline();
  let emitted = 0;
  p.onSample(() => emitted++);
  p.pushAccel(1_000_000, 0, 0, 9.81); // 1 ms
  // gyro 300 ms later — beyond MAX_PAIRING_DELTA_MS (25 ms) too
  p.pushGyro(301_000_000, 0, 0, 0);
  eq(emitted, 0);
  truthy(p.getStats().droppedNoPair >= 1);
});
t("duplicate timestamp is skipped", () => {
  const p = new SensorPipeline();
  p.pushAccel(2_000_000, 0, 0, 9.81);
  p.pushAccel(2_000_000, 0, 0, 9.81);
  truthy(p.getStats().duplicatesSkipped >= 1);
});
t("nearest-ts pairing works", () => {
  const p = new SensorPipeline();
  let s: any = null;
  p.onSample((x) => (s = x));
  p.pushAccel(1_000_000, 1, 2, 3);
  p.pushAccel(11_000_000, 4, 5, 6);
  p.pushGyro(12_000_000, 0.1, 0.2, 0.3); // nearest is accel@11ms
  truthy(s);
  eq(s.ax, 4);
});

console.log(`\n${PASS} passed, ${FAIL} failed`);
if (FAIL > 0) process.exit(1);
