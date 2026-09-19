// JS/TS simulator of the Member 5 native engine.
//
// STATUS: NOT VALIDATED as a functional replacement for the real Member 5
// C ABI. This file exists purely to (a) exercise the NavigationState
// contract, (b) drive Member 6 UI/diagnostics, and (c) reproduce the
// GNSS-outage / dead-reckoning workflow. A production Android build must
// swap this class for a JNI bridge into libmember5.so.
//
// C ABI mirror:
//   int   idr_init(config);
//   int   idr_feed_imu(sample);
//   int   idr_feed_gnss(sample);
//   void  idr_get_state(NavigationState*);
//   int   idr_shutdown();
//
// Dead-reckoning: when GNSS is fresh, state tracks GNSS position + speed.
// When GNSS is stale (>gnssStaleMs), Member 1 ONNX model predicts speed
// from the IMU ring buffer; heading is held from last GNSS bearing.
// This replaces the previous frozen-speed behaviour.

import {
  GnssSample,
  ImuSample,
  MapMatchStatus,
  NavigationMode,
  NavigationState,
  RejectionReason,
  VALIDITY,
  emptyNavigationState,
} from "../navigation/types";
import { evaluateSpeed } from "../safety/SpeedGuard";
import {
  BUILTIN_REGIONS,
  RoadPackRegion,
  selectRegion,
} from "../maps/RegionSelector";
import { OnnxSpeedEstimator } from "./OnnxSpeedEstimator";

export interface EngineConfig {
  regions?: RoadPackRegion[];
  gnssStaleMs?: number;
  drDecayPerSec?: number;
  onnxEstimator?: OnnxSpeedEstimator;
}

export class MemberFiveEngine {
  private state: NavigationState = emptyNavigationState();
  private lastImuTsNs = 0;
  private lastGnssWallMs = 0;
  private lastGnssTsNs = 0;
  private initialized = false;
  private regions: RoadPackRegion[];
  private activeRegion: RoadPackRegion | null = null;
  private gnssStaleMs: number;
  private drDecayPerSec: number;
  private lastRejection: RejectionReason = RejectionReason.NONE;
  private engineFault = false;

  // Member 1 ONNX speed estimator — predicts speed from IMU when GPS is lost.
  private onnxEstimator: OnnxSpeedEstimator | null = null;
  // Tracks whether an async ML inference is already in flight.
  private inferInFlight = false;

  // Injected override — used by the Simulation screen to publish an
  // impossible NavigationState.speedMps so we can exercise Member 6's
  // downstream guard without corrupting the engine's own math.
  private injectedSpeedMps: number | null = null;

  constructor(cfg: EngineConfig = {}) {
    this.regions = cfg.regions ?? BUILTIN_REGIONS;
    this.gnssStaleMs = cfg.gnssStaleMs ?? 3000;
    this.drDecayPerSec = cfg.drDecayPerSec ?? 0.05;
    this.onnxEstimator = cfg.onnxEstimator ?? null;
  }


  init(): boolean {
    this.state = emptyNavigationState();
    this.state.mode = NavigationMode.UNINITIALIZED;
    this.initialized = true;
    this.engineFault = false;
    return true;
  }

  shutdown(): void {
    this.initialized = false;
    this.state = emptyNavigationState();
    this.activeRegion = null;
    this.onnxEstimator?.reset();
  }

  isInitialized(): boolean {
    return this.initialized;
  }

  feedImu(sample: ImuSample): void {
    if (!this.initialized || this.engineFault) return;
    if (sample.timestampNs <= this.lastImuTsNs) {
      this.lastRejection = RejectionReason.TIMESTAMP_REGRESSION;
      return;
    }
    this.lastImuTsNs = sample.timestampNs;

    // Always push to ONNX ring buffer so it is primed when GPS drops.
    this.onnxEstimator?.pushSample(
      sample.ax, sample.ay, sample.az,
      sample.gx, sample.gy, sample.gz,
    );

    // Propagate dead-reckoning position if GNSS is stale.
    const nowMs = Date.now();
    const gnssAgeMs = nowMs - this.lastGnssWallMs;
    if (this.lastGnssWallMs > 0 && gnssAgeMs > this.gnssStaleMs) {
      const dtSec =
        this.state.timestampNs > 0
          ? Math.max(0, (sample.timestampNs - this.state.timestampNs) / 1e9)
          : 0;
      if (dtSec > 0 && dtSec < 1.0) {
        // Gyro Z heading integration: update yawRad dynamically when turning
        if (Number.isFinite(sample.gz)) {
          this.state.yawRad += sample.gz * dtSec;
          // Wrap heading to [-PI, PI]
          this.state.yawRad = Math.atan2(
            Math.sin(this.state.yawRad),
            Math.cos(this.state.yawRad),
          );
        }

        // ML speed update: fire async inference, but never block feedImu.
        // inferInFlight guards against queueing up hundreds of concurrent
        // promises at 100 Hz — only one runs at a time.
        if (this.onnxEstimator?.isLoaded() && !this.inferInFlight) {
          this.inferInFlight = true;
          this.onnxEstimator.infer().then((r) => {
            // r.speedMps is the ML predicted ground speed.
            // Decompose into ENU components using real-time gyro-updated heading.
            const spd = Math.max(0, r.speedMps);
            const yaw = this.state.yawRad;
            this.state.speedMps = spd;
            this.state.vEastMps  = spd * Math.cos(yaw);
            this.state.vNorthMps = spd * Math.sin(yaw);
            // Blend ML confidence into navigation confidence (decays as before).
            this.state.confidence = Math.min(this.state.confidence, r.confidence);
            this.inferInFlight = false;
          }).catch(() => { this.inferInFlight = false; });
        } else {
          // Keep velocity components aligned with current gyro-integrated yaw
          const spd = Math.max(0, this.state.speedMps);
          const yaw = this.state.yawRad;
          this.state.vEastMps  = spd * Math.cos(yaw);
          this.state.vNorthMps = spd * Math.sin(yaw);
        }

        // Position integration using current vEast/vNorth
        // (set by ML callback above or held from last GNSS).
        const dEast  = this.state.vEastMps  * dtSec;
        const dNorth = this.state.vNorthMps * dtSec;
        const cosLat = Math.max(
          0.01,
          Math.cos((this.state.latitudeDeg * Math.PI) / 180),
        );
        this.state.latitudeDeg  += dNorth / 111_320;
        this.state.longitudeDeg += dEast  / (111_320 * cosLat);
        this.state.confidence = Math.max(
          0,
          this.state.confidence - this.drDecayPerSec * dtSec,
        );
      }

      this.state.mode = NavigationMode.DEAD_RECKONING;
    }
    this.state.timestampNs = sample.timestampNs;
    this.refreshMapMatch();
  }


  feedGnss(sample: GnssSample): void {
    if (!this.initialized || this.engineFault) return;
    if (!sample.available) {
      // Explicit GNSS outage marker.
      const nowMs = Date.now();
      if (nowMs - this.lastGnssWallMs > this.gnssStaleMs) {
        this.state.mode = NavigationMode.DEAD_RECKONING;
      }
      return;
    }
    if (
      !Number.isFinite(sample.latitudeDeg) ||
      !Number.isFinite(sample.longitudeDeg)
    ) {
      this.lastRejection = RejectionReason.NAN_POSITION;
      return;
    }

    // Reject upstream absurd GNSS speed too (Member 1/3 responsibility,
    // but the engine also refuses to trust it).
    const speedEval = evaluateSpeed(sample.speedMps);
    const trustedSpeed = speedEval.valid ? sample.speedMps : 0;

    this.lastGnssTsNs = sample.timestampNs;
    this.lastGnssWallMs = Date.now();

    // Velocity components from GNSS speed + bearing when available.
    if (sample.bearingRad !== null && Number.isFinite(sample.bearingRad)) {
      // bearing here treated as ENU heading (rad, CCW from +East).
      this.state.vEastMps = trustedSpeed * Math.cos(sample.bearingRad);
      this.state.vNorthMps = trustedSpeed * Math.sin(sample.bearingRad);
      this.state.yawRad = sample.bearingRad;
    }

    this.state.latitudeDeg = sample.latitudeDeg;
    this.state.longitudeDeg = sample.longitudeDeg;
    this.state.altitudeM = sample.altitudeM;
    this.state.speedMps = trustedSpeed;
    this.state.timestampNs = sample.timestampNs;

    // Confidence from accuracy — 0 m error -> 1.0, 50 m -> ~0.
    const acc = Math.max(0, sample.horizontalAccuracyM);
    this.state.confidence = Math.max(0, Math.min(1, 1 - acc / 50));

    this.state.mode =
      acc > 20 ? NavigationMode.GNSS_DEGRADED : NavigationMode.GNSS;

    this.state.validity =
      VALIDITY.POSITION |
      VALIDITY.VELOCITY |
      VALIDITY.YAW |
      VALIDITY.SPEED |
      VALIDITY.CONFIDENCE;

    this.refreshMapMatch();
  }

  getState(): NavigationState {
    // Apply any injected impossible speed (Simulation screen only).
    if (this.injectedSpeedMps !== null) {
      return {
        ...this.state,
        speedMps: this.injectedSpeedMps,
        lastRejection: this.lastRejection,
      };
    }
    // Force stale mode if GNSS is old and no injection.
    const gnssAgeMs = Date.now() - this.lastGnssWallMs;
    let mode = this.state.mode;
    if (this.engineFault) {
      mode = NavigationMode.FAULT;
    } else if (
      this.lastGnssWallMs > 0 &&
      gnssAgeMs > this.gnssStaleMs &&
      mode !== NavigationMode.UNINITIALIZED
    ) {
      mode = NavigationMode.DEAD_RECKONING;
    }
    return { ...this.state, mode, lastRejection: this.lastRejection };
  }

  // ---- test / simulation hooks ----
  injectSpeedMps(v: number | null) {
    this.injectedSpeedMps = v;
  }

  simulateFault(on: boolean) {
    this.engineFault = on;
    if (on) this.lastRejection = RejectionReason.ENGINE_FAULT;
    else this.lastRejection = RejectionReason.NONE;
  }

  getActiveRegion(): RoadPackRegion | null {
    return this.activeRegion;
  }

  getGnssAgeMs(): number {
    if (this.lastGnssWallMs === 0) return -1;
    return Date.now() - this.lastGnssWallMs;
  }

  private refreshMapMatch() {
    const { latitudeDeg, longitudeDeg } = this.state;
    if (!Number.isFinite(latitudeDeg) || !Number.isFinite(longitudeDeg)) {
      this.state.mapMatchStatus = MapMatchStatus.UNAVAILABLE;
      this.state.mapRegionId = null;
      return;
    }
    const sel = selectRegion(
      latitudeDeg,
      longitudeDeg,
      this.regions,
      this.activeRegion,
    );
    this.activeRegion = sel.active;
    if (sel.outOfCoverage || !sel.active) {
      this.state.mapMatchStatus = MapMatchStatus.NO_REGION;
      this.state.mapRegionId = null;
    } else {
      this.state.mapMatchStatus =
        this.state.mode === NavigationMode.DEAD_RECKONING
          ? MapMatchStatus.DEGRADED
          : MapMatchStatus.MATCHED;
      this.state.mapRegionId = sel.active.regionId;
      this.state.validity |= VALIDITY.MAP_MATCH;
    }
  }
}
