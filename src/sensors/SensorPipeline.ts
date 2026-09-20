// Sensor Pipeline: Ingestion, Monotonic Guard, Timestamp-aware Pairing, Rate Accounting
import { GnssSample, ImuSample, SensorStats } from "../types";

export class SensorPipeline {
  private lastAccelTs = 0;
  private lastGyroTs = 0;
  private lastPairedTs = 0;
  private accelCount = 0;
  private gyroCount = 0;
  private emittedCount = 0;
  private lastHzCheck = Date.now();

  private stats: SensorStats = {
    accelHz: 0,
    gyroHz: 0,
    emittedHz: 0,
    lastPairingDeltaMs: 0.12,
    droppedRegression: 0,
    droppedStale: 0,
    droppedNoPair: 0,
    duplicatesSkipped: 0,
  };

  private imuListener: ((s: ImuSample) => void) | null = null;
  private gnssListener: ((s: GnssSample) => void) | null = null;

  // Unpaired buffer
  private latestAccel: { ax: number; ay: number; az: number; ts: number } | null = null;
  private latestGyro: { gx: number; gy: number; gz: number; ts: number } | null = null;

  onImu(cb: (s: ImuSample) => void) {
    this.imuListener = cb;
  }

  onGnss(cb: (s: GnssSample) => void) {
    this.gnssListener = cb;
  }

  feedRawAccel(ax: number, ay: number, az: number, tsNs: number) {
    if (tsNs <= this.lastAccelTs) {
      this.stats.droppedRegression++;
      return;
    }
    this.lastAccelTs = tsNs;
    this.accelCount++;
    this.latestAccel = { ax, ay, az, ts: tsNs };
    this.tryPair();
  }

  feedRawGyro(gx: number, gy: number, gz: number, tsNs: number) {
    if (tsNs <= this.lastGyroTs) {
      this.stats.droppedRegression++;
      return;
    }
    this.lastGyroTs = tsNs;
    this.gyroCount++;
    this.latestGyro = { gx, gy, gz, ts: tsNs };
    this.tryPair();
  }

  feedRawGnss(sample: GnssSample) {
    if (this.gnssListener) {
      this.gnssListener(sample);
    }
  }

  feedPairedImu(sample: ImuSample) {
    if (sample.timestampNs <= this.lastPairedTs) {
      this.stats.droppedRegression++;
      return;
    }
    this.lastPairedTs = sample.timestampNs;
    this.accelCount++;
    this.gyroCount++;
    this.emittedCount++;
    this.updateRates();

    if (this.imuListener) {
      this.imuListener(sample);
    }
  }

  private tryPair() {
    if (!this.latestAccel || !this.latestGyro) return;

    const deltaMs = Math.abs(this.latestAccel.ts - this.latestGyro.ts) / 1_000_000;
    this.stats.lastPairingDeltaMs = deltaMs;

    // Stale threshold 150ms
    if (deltaMs > 150) {
      this.stats.droppedStale++;
      if (this.latestAccel.ts < this.latestGyro.ts) {
        this.latestAccel = null;
      } else {
        this.latestGyro = null;
      }
      return;
    }

    const meanTs = Math.floor((this.latestAccel.ts + this.latestGyro.ts) / 2);
    if (meanTs <= this.lastPairedTs) {
      this.stats.duplicatesSkipped++;
      return;
    }

    this.lastPairedTs = meanTs;
    this.emittedCount++;
    this.updateRates();

    const sample: ImuSample = {
      timestampNs: meanTs,
      ax: this.latestAccel.ax,
      ay: this.latestAccel.ay,
      az: this.latestAccel.az,
      gx: this.latestGyro.gx,
      gy: this.latestGyro.gy,
      gz: this.latestGyro.gz,
    };

    if (this.imuListener) {
      this.imuListener(sample);
    }
  }

  private updateRates() {
    const now = Date.now();
    const elapsed = (now - this.lastHzCheck) / 1000;
    if (elapsed >= 1.0) {
      this.stats.accelHz = this.accelCount / elapsed;
      this.stats.gyroHz = this.gyroCount / elapsed;
      this.stats.emittedHz = this.emittedCount / elapsed;
      this.accelCount = 0;
      this.gyroCount = 0;
      this.emittedCount = 0;
      this.lastHzCheck = now;
    }
  }

  getStats(): SensorStats {
    return { ...this.stats };
  }

  reset() {
    this.lastAccelTs = 0;
    this.lastGyroTs = 0;
    this.lastPairedTs = 0;
    this.accelCount = 0;
    this.gyroCount = 0;
    this.emittedCount = 0;
    this.latestAccel = null;
    this.latestGyro = null;
    this.stats = {
      accelHz: 0,
      gyroHz: 0,
      emittedHz: 0,
      lastPairingDeltaMs: 0.12,
      droppedRegression: 0,
      droppedStale: 0,
      droppedNoPair: 0,
      duplicatesSkipped: 0,
    };
  }
}
