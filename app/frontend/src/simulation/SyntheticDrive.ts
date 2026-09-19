// Development-only synthetic drive generator.
// Feeds an EngineController with fabricated IMU + GNSS to exercise
// Member 6 UI without physical driving. Never enabled by default.

import { GnssSample, ImuSample } from "../navigation/types";

export type Scenario =
  | "STATIONARY"
  | "CONSTANT_50KMH"
  | "ACCELERATION"
  | "BRAKING"
  | "TURN"
  | "GNSS_OUTAGE"
  | "NOISY_IMU";

export interface SyntheticState {
  scenario: Scenario;
  gnssEnabled: boolean;
  running: boolean;
}

// Base coord — Bengaluru center to hit the demo region.
const BASE_LAT = 12.9716;
const BASE_LON = 77.5946;

export class SyntheticDrive {
  private t0Ms = 0;
  private timerImu: any = null;
  private timerGnss: any = null;
  private state: SyntheticState = {
    scenario: "STATIONARY",
    gnssEnabled: true,
    running: false,
  };
  private imuCb: ((s: ImuSample) => void) | null = null;
  private gnssCb: ((s: GnssSample) => void) | null = null;

  onImu(cb: (s: ImuSample) => void) {
    this.imuCb = cb;
  }
  onGnss(cb: (s: GnssSample) => void) {
    this.gnssCb = cb;
  }

  start() {
    if (this.state.running) return;
    this.state.running = true;
    this.t0Ms = Date.now();
    // 100 Hz IMU
    this.timerImu = setInterval(() => this.tickImu(), 10);
    // 1 Hz GNSS
    this.timerGnss = setInterval(() => this.tickGnss(), 1000);
  }

  stop() {
    this.state.running = false;
    if (this.timerImu) clearInterval(this.timerImu);
    if (this.timerGnss) clearInterval(this.timerGnss);
    this.timerImu = this.timerGnss = null;
  }

  setScenario(s: Scenario) {
    this.state.scenario = s;
    if (s === "GNSS_OUTAGE") this.state.gnssEnabled = false;
    else this.state.gnssEnabled = true;
  }

  setGnssEnabled(v: boolean) {
    this.state.gnssEnabled = v;
  }

  getState(): SyntheticState {
    return { ...this.state };
  }

  private tickImu() {
    const tsNs = BigIntSafeNs();
    const t = (Date.now() - this.t0Ms) / 1000;
    let ax = 0,
      ay = 0,
      az = 9.81;
    let gx = 0,
      gy = 0,
      gz = 0;
    switch (this.state.scenario) {
      case "ACCELERATION":
        ax = 1.5;
        break;
      case "BRAKING":
        ax = -2.0;
        break;
      case "TURN":
        gz = 0.5; // rad/s yaw rate
        ax = 0.5;
        break;
      case "NOISY_IMU":
        ax = (Math.random() - 0.5) * 2;
        ay = (Math.random() - 0.5) * 2;
        gz = (Math.random() - 0.5) * 1;
        break;
      case "CONSTANT_50KMH":
        // Small road noise
        ax = 0.02 * Math.sin(t * 3);
        break;
    }
    this.imuCb?.({ timestampNs: tsNs, ax, ay, az, gx, gy, gz });
  }

  private tickGnss() {
    if (!this.state.gnssEnabled) {
      this.gnssCb?.({
        timestampNs: BigIntSafeNs(),
        latitudeDeg: BASE_LAT,
        longitudeDeg: BASE_LON,
        altitudeM: 900,
        speedMps: 0,
        bearingRad: 0,
        horizontalAccuracyM: 999,
        available: false,
      });
      return;
    }
    const t = (Date.now() - this.t0Ms) / 1000;
    let speedMps = 0;
    let bearingRad = 0; // East
    switch (this.state.scenario) {
      case "CONSTANT_50KMH":
        speedMps = 50 / 3.6;
        break;
      case "ACCELERATION":
        speedMps = Math.min(30, 1.5 * t);
        break;
      case "BRAKING":
        speedMps = Math.max(0, 20 - 2 * t);
        break;
      case "TURN":
        speedMps = 40 / 3.6;
        bearingRad = (t * 0.2) % (2 * Math.PI);
        break;
    }
    // Move east from base by integrated speed (approx).
    const lonOffset =
      (speedMps * t) / (111_320 * Math.cos((BASE_LAT * Math.PI) / 180));
    this.gnssCb?.({
      timestampNs: BigIntSafeNs(),
      latitudeDeg: BASE_LAT,
      longitudeDeg: BASE_LON + lonOffset,
      altitudeM: 900,
      speedMps,
      bearingRad,
      horizontalAccuracyM: 5,
      available: true,
    });
  }
}

function BigIntSafeNs(): number {
  // performance.now() is µs-resolution; multiply to ns without BigInt.
  return Math.floor(
    (typeof performance !== "undefined" ? performance.now() : Date.now()) *
      1_000_000,
  );
}
