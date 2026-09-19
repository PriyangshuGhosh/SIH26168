// NavigationState contract mirrors the Member 5 native C ABI struct.
// All fields, units and validity flags MUST match the native side so the
// TS engine can be swapped for a real JNI/FFI bridge without breaking Member 6.
//
// Units are canonical SI:
//   position:   latitude/longitude in degrees, altitude in meters
//   velocity:   m/s (body/world frame irrelevant here — engine emits ground speed)
//   yaw:        radians, [-pi, pi], world frame (ENU heading from +East, CCW positive)
//   speed:      m/s scalar, always >= 0 when valid
//   confidence: [0..1]
//
// The `mode` mirrors Member 5's navigation_mode enum.
// The `mapMatchStatus` mirrors Member 4's status enum.
// The `validity` bitfield mirrors Member 5's field validity flags.

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

// Bit flags for per-field validity, matching the native validity bitfield.
export const VALIDITY = {
  POSITION: 1 << 0,
  VELOCITY: 1 << 1,
  YAW: 1 << 2,
  SPEED: 1 << 3,
  CONFIDENCE: 1 << 4,
  MAP_MATCH: 1 << 5,
} as const;

export interface NavigationState {
  // Monotonic engine timestamp in nanoseconds (matches native clock_gettime).
  timestampNs: number;

  // Position (WGS84).
  latitudeDeg: number;
  longitudeDeg: number;
  altitudeM: number;

  // Ground-plane velocity components (m/s, ENU).
  vEastMps: number;
  vNorthMps: number;

  // Scalar ground speed (m/s).
  speedMps: number;

  // Heading (rad, ENU, CCW positive from +East). Engine yaw, NOT phone yaw.
  yawRad: number;

  // [0..1].
  confidence: number;

  mode: NavigationMode;
  mapMatchStatus: MapMatchStatus;

  // Active offline map region ID (or null if none loaded).
  mapRegionId: string | null;

  // Bitmask from VALIDITY. Bit unset => field is not trustworthy.
  validity: number;

  // Last rejection reason from the safety layer. NONE when nominal.
  lastRejection: RejectionReason;
}

export function emptyNavigationState(): NavigationState {
  return {
    timestampNs: 0,
    latitudeDeg: 0,
    longitudeDeg: 0,
    altitudeM: 0,
    vEastMps: 0,
    vNorthMps: 0,
    speedMps: 0,
    yawRad: 0,
    confidence: 0,
    mode: NavigationMode.UNINITIALIZED,
    mapMatchStatus: MapMatchStatus.UNAVAILABLE,
    mapRegionId: null,
    validity: 0,
    lastRejection: RejectionReason.NONE,
  };
}

// IMU sample as delivered to Member 5's idr_feed_imu.
// accel: m/s^2, gyro: rad/s, ts in ns (monotonic).
export interface ImuSample {
  timestampNs: number;
  ax: number;
  ay: number;
  az: number;
  gx: number;
  gy: number;
  gz: number;
}

// GNSS sample as delivered to Member 5's idr_feed_gnss.
export interface GnssSample {
  timestampNs: number;
  latitudeDeg: number;
  longitudeDeg: number;
  altitudeM: number;
  speedMps: number;
  bearingRad: number | null; // null => unknown
  horizontalAccuracyM: number;
  available: boolean;
}
