// Timestamp-aware IMU pairing.
//
// Android accelerometer and gyroscope callbacks fire independently at ~100 Hz.
// We must NOT blindly pair the latest of each. Strategy:
//
//   - Buffer the most recent 8 accelerometer samples (ring buffer).
//   - When a gyro sample arrives, interpolate/pick the nearest accel sample
//     whose |dt| < MAX_PAIRING_DELTA_MS. Emit a paired ImuSample at gyro's
//     timestamp. This preserves gyro cadence (used by EKF).
//   - Detect monotonic timestamp regression -> drop sample.
//   - Detect stale sample (delta > STALE_MS) -> mark stale.
//   - Deduplicate identical timestamps.
//
// The Expo web sensors emulation and expo-sensors both deliver
// { x, y, z } tuples plus DeviceMotion timestamp. We normalize to ns.

import { ImuSample } from "../navigation/types";

const RING_SIZE = 8;
const MAX_PAIRING_DELTA_MS = 25; // ~2 sample periods at 100 Hz
const STALE_MS = 200;

interface AccelBufItem {
  tsNs: number;
  x: number;
  y: number;
  z: number;
}

export interface SensorStats {
  accelHz: number;
  gyroHz: number;
  emittedHz: number;
  lastPairingDeltaMs: number;
  droppedRegression: number;
  droppedStale: number;
  droppedNoPair: number;
  duplicatesSkipped: number;
  lastAccelTsNs: number;
  lastGyroTsNs: number;
  lastEmitTsNs: number;
}

export class SensorPipeline {
  private accelBuf: AccelBufItem[] = [];
  private accelHead = 0;
  private accelCount = 0;

  private lastEmitTsNs = 0;
  private lastAccelTsNs = 0;
  private lastGyroTsNs = 0;

  private accelTicksWindow: number[] = [];
  private gyroTicksWindow: number[] = [];
  private emitTicksWindow: number[] = [];

  private droppedRegression = 0;
  private droppedStale = 0;
  private droppedNoPair = 0;
  private duplicatesSkipped = 0;

  private lastPairingDeltaMs = 0;

  private emitCb: ((s: ImuSample) => void) | null = null;

  onSample(cb: (s: ImuSample) => void) {
    this.emitCb = cb;
  }

  // Accelerometer callback. Units: m/s^2.
  pushAccel(tsNs: number, x: number, y: number, z: number): void {
    if (tsNs <= this.lastAccelTsNs) {
      // regression or duplicate
      if (tsNs === this.lastAccelTsNs) this.duplicatesSkipped++;
      else this.droppedRegression++;
      return;
    }
    this.lastAccelTsNs = tsNs;
    this.pushTick(this.accelTicksWindow, tsNs);

    const idx = this.accelHead % RING_SIZE;
    this.accelBuf[idx] = { tsNs, x, y, z };
    this.accelHead++;
    if (this.accelCount < RING_SIZE) this.accelCount++;
  }

  // Gyroscope callback. Units: rad/s.
  pushGyro(tsNs: number, x: number, y: number, z: number): void {
    if (tsNs <= this.lastGyroTsNs) {
      if (tsNs === this.lastGyroTsNs) this.duplicatesSkipped++;
      else this.droppedRegression++;
      return;
    }
    this.lastGyroTsNs = tsNs;
    this.pushTick(this.gyroTicksWindow, tsNs);

    if (this.accelCount === 0) {
      this.droppedNoPair++;
      return;
    }

    // Find nearest accel sample by |dt|.
    let bestIdx = -1;
    let bestDeltaNs = Number.POSITIVE_INFINITY;
    for (let i = 0; i < this.accelCount; i++) {
      const s = this.accelBuf[i];
      if (!s) continue;
      const d = Math.abs(s.tsNs - tsNs);
      if (d < bestDeltaNs) {
        bestDeltaNs = d;
        bestIdx = i;
      }
    }
    if (bestIdx < 0) {
      this.droppedNoPair++;
      return;
    }
    const acc = this.accelBuf[bestIdx];
    const deltaMs = bestDeltaNs / 1e6;
    this.lastPairingDeltaMs = deltaMs;

    if (deltaMs > MAX_PAIRING_DELTA_MS) {
      this.droppedNoPair++;
      return;
    }
    if ((tsNs - acc.tsNs) / 1e6 > STALE_MS) {
      this.droppedStale++;
      return;
    }
    if (tsNs <= this.lastEmitTsNs) {
      this.droppedRegression++;
      return;
    }

    const sample: ImuSample = {
      timestampNs: tsNs,
      ax: acc.x,
      ay: acc.y,
      az: acc.z,
      gx: x,
      gy: y,
      gz: z,
    };
    this.lastEmitTsNs = tsNs;
    this.pushTick(this.emitTicksWindow, tsNs);
    this.emitCb?.(sample);
  }

  getStats(): SensorStats {
    return {
      accelHz: hzFromWindow(this.accelTicksWindow),
      gyroHz: hzFromWindow(this.gyroTicksWindow),
      emittedHz: hzFromWindow(this.emitTicksWindow),
      lastPairingDeltaMs: this.lastPairingDeltaMs,
      droppedRegression: this.droppedRegression,
      droppedStale: this.droppedStale,
      droppedNoPair: this.droppedNoPair,
      duplicatesSkipped: this.duplicatesSkipped,
      lastAccelTsNs: this.lastAccelTsNs,
      lastGyroTsNs: this.lastGyroTsNs,
      lastEmitTsNs: this.lastEmitTsNs,
    };
  }

  reset() {
    this.accelBuf = [];
    this.accelHead = 0;
    this.accelCount = 0;
    this.lastEmitTsNs = 0;
    this.lastAccelTsNs = 0;
    this.lastGyroTsNs = 0;
    this.accelTicksWindow = [];
    this.gyroTicksWindow = [];
    this.emitTicksWindow = [];
    this.droppedRegression = 0;
    this.droppedStale = 0;
    this.droppedNoPair = 0;
    this.duplicatesSkipped = 0;
    this.lastPairingDeltaMs = 0;
  }

  private pushTick(win: number[], tsNs: number) {
    win.push(tsNs);
    const cutoff = tsNs - 1_000_000_000; // last 1s
    while (win.length && win[0] < cutoff) win.shift();
  }
}

function hzFromWindow(win: number[]): number {
  if (win.length < 2) return 0;
  const spanNs = win[win.length - 1] - win[0];
  if (spanNs <= 0) return 0;
  return ((win.length - 1) * 1e9) / spanNs;
}
