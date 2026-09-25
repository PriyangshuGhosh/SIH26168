// SIH26168 Navigation State & Sensor Types
// Mirrors the Member 5 C ABI contract

export enum NavigationMode {
  UNINITIALIZED = "UNINITIALIZED",
  GNSS = "GNSS",
  GNSS_DEGRADED = "GNSS_DEGRADED",
  DEAD_RECKONING = "DEAD_RECKONING",
  FAULT = "FAULT",
}

export enum MapMatchStatus {
  UNAVAILABLE = "UNAVAILABLE",
  NO_REGION = "NO_REGION",
  MATCHED = "MATCHED",
  DEGRADED = "DEGRADED",
  LOST = "LOST",
}

export enum RejectionReason {
  NONE = "NONE",
  NAN_SPEED = "NAN_SPEED",
  INF_SPEED = "INF_SPEED",
  NEGATIVE_SPEED = "NEGATIVE_SPEED",
  ABSURD_SPEED = "ABSURD_SPEED",
  STALE_SAMPLE = "STALE_SAMPLE",
  TIMESTAMP_REGRESSION = "TIMESTAMP_REGRESSION",
  NAN_POSITION = "NAN_POSITION",
  NAN_YAW = "NAN_YAW",
  ENGINE_FAULT = "ENGINE_FAULT",
}

export const VALIDITY = {
  POSITION: 1 << 0,
  VELOCITY: 1 << 1,
  YAW: 1 << 2,
  SPEED: 1 << 3,
  CONFIDENCE: 1 << 4,
  MAP_MATCH: 1 << 5,
} as const;

export interface MlPredictionRecord {
  velocity_mps: number;
  velocity_variance_m2s2: number;
  confidence: number;
  inference_time_ms: number;
  timestamp: number;
  model: string;
}

export interface NavigationState {
  timestampNs: number;
  latitudeDeg: number;
  longitudeDeg: number;
  altitudeM: number;
  vEastMps: number;
  vNorthMps: number;
  speedMps: number;
  yawRad: number;
  confidence: number;
  mode: NavigationMode;
  mapMatchStatus: MapMatchStatus;
  mapRegionId: string | null;
  validity: number;
  lastRejection: RejectionReason;
  // Member 1 Machine Learning State
  mlModelActive: boolean;
  mlSpeedMps: number | null;
  mlVarianceM2s2: number | null;
  mlConfidence: number | null;
  mlInferenceTimeMs: number | null;
  mlInferenceCount: number;
  mlModelName: string;
  mlLastPredictionTs: number;
  // Dual-Track Dead Reckoning comparison
  unconstrainedDrLatDeg: number;
  unconstrainedDrLonDeg: number;
  driftErrorMeters: number;
  // Outage diagnostics
  outageDurationSec: number;
  tunnelDistanceMeters: number;
  // Member 2 Frame Alignment
  alignmentStatus: number;
  alignmentConfidence: number;
  // Member 4 Map Matching
  matchedRoadName: string | null;
  distanceToRoadMeters: number | null;
  // Optional road-corridor constraint (off by default for backward compatibility)
  roadConstraintEnabled: boolean;
  roadConstraintActive: boolean;
  roadConstraintConfidence: number;
  roadConstraintOffsetMeters: number | null;
  roadConstraintCorrectionMeters: number;
}

export function emptyNavigationState(): NavigationState {
  return {
    timestampNs: 0,
    latitudeDeg: 17.6868,
    longitudeDeg: 83.2185,
    altitudeM: 14.5,
    vEastMps: 0,
    vNorthMps: 0,
    speedMps: 0,
    yawRad: 0,
    confidence: 0,
    mode: NavigationMode.UNINITIALIZED,
    mapMatchStatus: MapMatchStatus.UNAVAILABLE,
    mapRegionId: "in-vizag",
    validity: 0,
    lastRejection: RejectionReason.NONE,
    mlModelActive: false,
    mlSpeedMps: null,
    mlVarianceM2s2: null,
    mlConfidence: null,
    mlInferenceTimeMs: null,
    mlInferenceCount: 0,
    mlModelName: "final.production.onnx",
    mlLastPredictionTs: 0,
    unconstrainedDrLatDeg: 17.6868,
    unconstrainedDrLonDeg: 83.2185,
    driftErrorMeters: 0,
    outageDurationSec: 0,
    tunnelDistanceMeters: 0,
    alignmentStatus: 4, // FULLY_ALIGNED
    alignmentConfidence: 0.92,
    matchedRoadName: "NH16 Simhachalam Corridor",
    distanceToRoadMeters: 1.2,
    roadConstraintEnabled: false,
    roadConstraintActive: false,
    roadConstraintConfidence: 0,
    roadConstraintOffsetMeters: null,
    roadConstraintCorrectionMeters: 0,
  };
}

export interface ImuSample {
  timestampNs: number;
  ax: number;
  ay: number;
  az: number;
  gx: number;
  gy: number;
  gz: number;
}

export interface GnssSample {
  timestampNs: number;
  latitudeDeg: number;
  longitudeDeg: number;
  altitudeM: number;
  speedMps: number;
  bearingRad: number | null;
  horizontalAccuracyM: number;
  available: boolean;
}

export interface SpeedEvaluation {
  valid: boolean;
  reason: RejectionReason;
  kmh: number | null;
}

export interface RoadPackRegion {
  regionId: string;
  name: string;
  minLatDeg: number;
  maxLatDeg: number;
  minLonDeg: number;
  maxLonDeg: number;
  version: string;
  source: "demo" | "provisioned";
}

export interface RegionSelectionResult {
  active: RoadPackRegion | null;
  outOfCoverage: boolean;
}

export type Scenario =
  | "SIMHACHALAM_TUNNEL"
  | "CONSTANT_50KMH"
  | "URBAN_CANYON"
  | "BRAKING_IN_TUNNEL"
  | "STOP_AND_GO"
  | "ACCELERATION"
  | "TURN"
  | "GNSS_OUTAGE"
  | "NOISY_IMU";

export interface SyntheticState {
  scenario: Scenario;
  gnssEnabled: boolean;
  running: boolean;
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
}
