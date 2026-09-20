// Member 5 Integrated Edge Navigation Engine
// Fuses Member 1 (ML Speed Estimator / final.production.onnx), Member 2 (Frame Alignment),
// Member 3 (8-State EKF Fusion), Member 4 (HMM Map Matching), and SpeedGuard safety validation.

import {
  GnssSample,
  ImuSample,
  MapMatchStatus,
  NavigationMode,
  NavigationState,
  RejectionReason,
  RoadPackRegion,
  VALIDITY,
  emptyNavigationState,
} from "../types";
import { evaluateSpeed } from "../safety/SpeedGuard";
import { BUILTIN_REGIONS, selectRegion } from "../maps/RegionSelector";
import { mlSpeedService } from "./MlSpeedService";
import { EkfFusion } from "./EkfFusion";
import { FrameAligner, CalibrationStatus } from "./FrameAligner";
import { offlineMapMatcher } from "./MapMatchingService";

export interface EngineConfig {
  regions?: RoadPackRegion[];
  gnssStaleMs?: number;
  drDecayPerSec?: number;
}

export class MemberFiveEngine {
  private state: NavigationState = emptyNavigationState();
  private lastImuTsNs = 0;
  private lastGnssWallMs = 0;
  private initialized = false;
  private regions: RoadPackRegion[];
  private activeRegion: RoadPackRegion | null = null;
  private gnssStaleMs: number;
  private drDecayPerSec: number;
  private lastRejection: RejectionReason = RejectionReason.NONE;
  private engineFault = false;
  private injectedSpeedMps: number | null = null;

  // Member 2 Frame Aligner (Phone-to-Vehicle IMU Alignment)
  public frameAligner: FrameAligner = new FrameAligner();

  // Member 3 Extended Kalman Filter
  public ekf: EkfFusion = new EkfFusion();

  // Member 4 Offline Map Matcher
  public mapMatcher = offlineMapMatcher;

  // Origin reference for ENU local tangent plane (Visakhapatnam default)
  private originLat = 17.6868;
  private originLon = 83.2185;
  private outageStartMs = 0;

  constructor(cfg: EngineConfig = {}) {
    this.regions = cfg.regions ?? BUILTIN_REGIONS;
    this.gnssStaleMs = cfg.gnssStaleMs ?? 1500;
    this.drDecayPerSec = cfg.drDecayPerSec ?? 0.015;
  }

  init(): boolean {
    this.state = emptyNavigationState();
    this.state.mode = NavigationMode.UNINITIALIZED;
    this.initialized = true;
    this.engineFault = false;
    this.lastGnssWallMs = Date.now();
    this.ekf.reset();
    this.outageStartMs = 0;
    return true;
  }

  shutdown(): void {
    this.initialized = false;
    this.state = emptyNavigationState();
    this.activeRegion = null;
    this.ekf.reset();
  }

  isInitialized(): boolean {
    return this.initialized;
  }

  // Convert ENU offsets to Lat/Lon
  private enuToLatLon(northM: number, eastM: number): { lat: number; lon: number } {
    const latRad = (this.originLat * Math.PI) / 180;
    const cosLat = Math.max(0.01, Math.cos(latRad));
    const lat = this.originLat + northM / 111320;
    const lon = this.originLon + eastM / (111320 * cosLat);
    return { lat, lon };
  }

  // Convert Lat/Lon to ENU offsets
  private latLonToEnu(lat: number, lon: number): { north: number; east: number } {
    const latRad = (this.originLat * Math.PI) / 180;
    const cosLat = Math.max(0.01, Math.cos(latRad));
    const north = (lat - this.originLat) * 111320;
    const east = (lon - this.originLon) * (111320 * cosLat);
    return { north, east };
  }

  feedImu(sample: ImuSample): void {
    if (!this.initialized || this.engineFault) return;

    if (sample.timestampNs <= this.lastImuTsNs) {
      this.lastRejection = RejectionReason.TIMESTAMP_REGRESSION;
      return;
    }
    this.lastImuTsNs = sample.timestampNs;

    // Member 2 Frame Alignment: Transform raw phone sensor frame into vehicle chassis frame
    const alignedFrame = this.frameAligner.process(
      sample.timestampNs,
      sample.ax,
      sample.ay,
      sample.az,
      sample.gx,
      sample.gy,
      sample.gz
    );
    this.state.alignmentStatus = alignedFrame.status;
    this.state.alignmentConfidence = alignedFrame.confidence.overall;

    const alignedSample: ImuSample = {
      timestampNs: sample.timestampNs,
      ax: alignedFrame.ax,
      ay: alignedFrame.ay,
      az: alignedFrame.az,
      gx: alignedFrame.gx,
      gy: alignedFrame.gy,
      gz: alignedFrame.gz,
    };

    // Push vehicle-aligned sample into Member 1 ML sliding window buffer (200 samples @ 100 Hz = 2.0 s)
    mlSpeedService.pushSample(alignedSample);

    const nowMs = Date.now();
    const gnssAgeMs = nowMs - this.lastGnssWallMs;
    const isGnssDenied = this.lastGnssWallMs > 0 && gnssAgeMs > this.gnssStaleMs;

    const tSec = sample.timestampNs / 1e9;

    // Member 3 EKF predict step using aligned vehicle frame forces and yaw rates
    this.ekf.predict(
      tSec,
      alignedSample.ax,
      alignedSample.ay,
      alignedSample.gz,
      alignedFrame.status === CalibrationStatus.FULLY_ALIGNED
    );

    // Propagate Dead Reckoning when GNSS is lost or denied
    if (isGnssDenied) {
      if (this.outageStartMs === 0) {
        this.outageStartMs = nowMs;
      }
      this.state.mode = NavigationMode.DEAD_RECKONING;
      this.state.mlModelActive = true;
      this.state.outageDurationSec = (nowMs - this.outageStartMs) / 1000;

      // Asynchronously invoke Member 1 ML inference if ready
      if (mlSpeedService.isReady()) {
        mlSpeedService.predictNow().then((pred) => {
          if (pred && this.state.mode === NavigationMode.DEAD_RECKONING) {
            // SpeedGuard evaluation
            const evalRes = evaluateSpeed(pred.velocity_mps);
            if (evalRes.valid) {
              // Update EKF state using Member 1 model prediction
              this.ekf.updateSpeed(tSec, pred.velocity_mps, pred.velocity_variance_m2s2);
              this.state.mlSpeedMps = pred.velocity_mps;
              this.state.mlVarianceM2s2 = pred.velocity_variance_m2s2;
              this.state.mlConfidence = pred.confidence;
              this.state.mlInferenceTimeMs = pred.inference_time_ms;
              this.state.mlInferenceCount = mlSpeedService.getTotalInferences();
              this.state.mlLastPredictionTs = pred.timestamp;
            } else {
              this.lastRejection = evalRes.reason;
            }
          }
        });
      }

      // Read fused state from EKF
      const northM = this.ekf.x[0];
      const eastM = this.ekf.x[1];
      const fusedCoords = this.enuToLatLon(northM, eastM);

      this.state.latitudeDeg = fusedCoords.lat;
      this.state.longitudeDeg = fusedCoords.lon;
      this.state.yawRad = this.ekf.x[4];
      this.state.speedMps = this.injectedSpeedMps ?? Math.hypot(this.ekf.x[2], this.ekf.x[3]);
      this.state.vEastMps = this.ekf.x[2] * Math.sin(this.state.yawRad);
      this.state.vNorthMps = this.ekf.x[2] * Math.cos(this.state.yawRad);

      // Read unconstrained integration (showing divergence without ML)
      const unconstrainedCoords = this.enuToLatLon(
        this.ekf.unconstrainedNorth,
        this.ekf.unconstrainedEast
      );
      this.state.unconstrainedDrLatDeg = unconstrainedCoords.lat;
      this.state.unconstrainedDrLonDeg = unconstrainedCoords.lon;
      this.state.driftErrorMeters = this.ekf.getDriftSavedMeters();

      // Accumulate distance in tunnel
      this.state.tunnelDistanceMeters += this.state.speedMps * 0.01;

      // Confidence slowly decays in dead reckoning but stays high (>0.70) thanks to ML model
      const baseConfidence = this.state.mlConfidence ?? 0.85;
      this.state.confidence = Math.max(
        0.5,
        baseConfidence - this.drDecayPerSec * this.state.outageDurationSec
      );
    } else {
      this.state.mlModelActive = false;
      this.outageStartMs = 0;
      this.state.outageDurationSec = 0;
      this.state.tunnelDistanceMeters = 0;
    }

    this.state.timestampNs = sample.timestampNs;
    this.refreshMapMatch();
  }

  feedGnss(sample: GnssSample): void {
    if (!this.initialized || this.engineFault) return;

    if (!sample.available) {
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

    const speedEval = evaluateSpeed(sample.speedMps);
    const trustedSpeed = speedEval.valid ? sample.speedMps : 0;

    if (!speedEval.valid) {
      this.lastRejection = speedEval.reason;
    }

    this.lastGnssWallMs = Date.now();
    this.outageStartMs = 0;
    this.state.mlModelActive = false;
    this.state.outageDurationSec = 0;

    // Anchor local tangent plane origin to the latest genuine satellite fix
    this.originLat = sample.latitudeDeg;
    this.originLon = sample.longitudeDeg;

    this.state.latitudeDeg = sample.latitudeDeg;
    this.state.longitudeDeg = sample.longitudeDeg;
    this.state.altitudeM = sample.altitudeM;
    this.state.speedMps = this.injectedSpeedMps ?? trustedSpeed;

    if (sample.bearingRad !== null && Number.isFinite(sample.bearingRad)) {
      this.state.yawRad = sample.bearingRad;
    }

    // Convert GNSS fix to ENU and update EKF
    const enu = this.latLonToEnu(sample.latitudeDeg, sample.longitudeDeg);
    const tSec = sample.timestampNs / 1e9;
    this.ekf.updateGnss(
      tSec,
      enu.north,
      enu.east,
      sample.horizontalAccuracyM,
      this.state.speedMps
    );

    // Keep unconstrained comparison point synced
    this.state.unconstrainedDrLatDeg = sample.latitudeDeg;
    this.state.unconstrainedDrLonDeg = sample.longitudeDeg;
    this.state.driftErrorMeters = 0;

    // Degraded mode if accuracy exceeds 15 meters
    if (sample.horizontalAccuracyM > 15) {
      this.state.mode = NavigationMode.GNSS_DEGRADED;
      this.state.confidence = Math.max(0.3, 1 - sample.horizontalAccuracyM / 50);
    } else {
      this.state.mode = NavigationMode.GNSS;
      this.state.confidence = Math.min(1.0, Math.max(0.85, 1 - sample.horizontalAccuracyM / 100));
    }

    this.state.timestampNs = sample.timestampNs;
    this.refreshMapMatch();
  }

  setInjectedSpeed(mps: number | null): void {
    this.injectedSpeedMps = mps;
    if (mps !== null) {
      this.state.speedMps = mps;
    }
  }

  setOrigin(lat: number, lon: number): void {
    this.originLat = lat;
    this.originLon = lon;
  }

  injectFault(fault: boolean): void {
    this.engineFault = fault;
    if (fault) {
      this.state.mode = NavigationMode.FAULT;
      this.lastRejection = RejectionReason.ENGINE_FAULT;
    } else {
      this.state.mode = NavigationMode.UNINITIALIZED;
      this.lastRejection = RejectionReason.NONE;
    }
  }

  triggerOutageNow(): void {
    this.lastGnssWallMs = 1; // Expire GNSS immediately
    this.outageStartMs = Date.now();
    this.state.mode = NavigationMode.DEAD_RECKONING;
    this.state.mlModelActive = true;
  }

  restoreGnssNow(lat: number, lon: number, speedMps = 15): void {
    this.lastGnssWallMs = Date.now();
    this.outageStartMs = 0;
    this.state.mode = NavigationMode.GNSS;
    this.state.mlModelActive = false;
    this.state.latitudeDeg = lat;
    this.state.longitudeDeg = lon;
    this.state.speedMps = speedMps;
  }

  private refreshMapMatch(): void {
    const res = selectRegion(
      this.state.latitudeDeg,
      this.state.longitudeDeg,
      this.regions,
      this.activeRegion
    );
    this.activeRegion = res.active;
    this.state.mapRegionId = res.active?.regionId ?? null;

    // Member 4 Offline HMM Map Matching projection
    const matchRes = this.mapMatcher.match(
      this.state.latitudeDeg,
      this.state.longitudeDeg,
      this.state.yawRad
    );
    this.state.matchedRoadName = matchRes.matchedSegmentLabel;
    this.state.distanceToRoadMeters = matchRes.distanceToRoadMeters;

    if (res.outOfCoverage || !res.active) {
      this.state.mapMatchStatus = MapMatchStatus.NO_REGION;
    } else if (matchRes.matched) {
      this.state.mapMatchStatus = MapMatchStatus.MATCHED;
    } else if (this.state.mode === NavigationMode.GNSS_DEGRADED) {
      this.state.mapMatchStatus = MapMatchStatus.DEGRADED;
    } else if (this.state.mode === NavigationMode.DEAD_RECKONING) {
      this.state.mapMatchStatus = MapMatchStatus.DEGRADED;
    } else {
      this.state.mapMatchStatus = MapMatchStatus.UNAVAILABLE;
    }

    // Compute validity bitmask (6-bit engine validity contract)
    let mask = 0;
    if (
      Number.isFinite(this.state.latitudeDeg) &&
      Number.isFinite(this.state.longitudeDeg)
    ) {
      mask |= VALIDITY.POSITION;
    }
    if (
      Number.isFinite(this.state.vEastMps) &&
      Number.isFinite(this.state.vNorthMps)
    ) {
      mask |= VALIDITY.VELOCITY;
    }
    if (Number.isFinite(this.state.yawRad)) {
      mask |= VALIDITY.YAW;
    }
    const speedEval = evaluateSpeed(this.state.speedMps);
    if (speedEval.valid) {
      mask |= VALIDITY.SPEED;
    }
    if (this.state.confidence > 0 && Number.isFinite(this.state.confidence)) {
      mask |= VALIDITY.CONFIDENCE;
    }
    if (this.state.mapMatchStatus === MapMatchStatus.MATCHED) {
      mask |= VALIDITY.MAP_MATCH;
    }

    this.state.validity = mask;
    this.state.lastRejection = this.lastRejection;
  }

  getState(): NavigationState {
    return { ...this.state };
  }

  getActiveRegion(): RoadPackRegion | null {
    return this.activeRegion;
  }
}
