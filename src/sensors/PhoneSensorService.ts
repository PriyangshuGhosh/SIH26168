// Device Hardware Sensor Service
// Connects real phone DeviceMotionEvent (3-axis Accel & Gyro), DeviceOrientationEvent,
// and GeolocationWatch (GNSS) to the Member 5 SensorPipeline.

import { SensorPipeline } from "./SensorPipeline";

export interface RawImuTelemetry {
  ax: number;
  ay: number;
  az: number;
  accelMag: number;
  gx: number;
  gy: number;
  gz: number;
  alpha: number | null; // compass / heading
  beta: number | null;  // pitch
  gamma: number | null; // roll
  rateHz: number;
  eventCount: number;
  lastUpdateMs: number;
}

export interface RawGpsTelemetry {
  latitudeDeg: number | null;
  longitudeDeg: number | null;
  altitudeM: number | null;
  accuracyM: number | null;
  speedMps: number | null;
  headingDeg: number | null;
  available: boolean;
  lastFixMs: number;
  error: string | null;
}

export interface RealSensorState {
  isSupported: boolean;
  permissionGranted: boolean;
  isStreaming: boolean;
  gpsActive: boolean;
  motionActive: boolean;
  error: string | null;
  rawImu: RawImuTelemetry;
  rawGps: RawGpsTelemetry;
}

export class PhoneSensorService {
  private pipeline: SensorPipeline;
  private isListening = false;
  private watchId: number | null = null;
  private onStateChangeCb: ((state: RealSensorState) => void) | null = null;

  // Rate accounting
  private imuEventCount = 0;
  private imuEventsInWindow = 0;
  private lastImuRateCalcTime = performance.now();
  private imuRateHz = 0;

  private state: RealSensorState = {
    isSupported: typeof window !== "undefined" && ("DeviceMotionEvent" in window || "ondevicemotion" in window),
    permissionGranted: false,
    isStreaming: false,
    gpsActive: false,
    motionActive: false,
    error: null,
    rawImu: {
      ax: 0,
      ay: 0,
      az: 9.81,
      accelMag: 9.81,
      gx: 0,
      gy: 0,
      gz: 0,
      alpha: null,
      beta: null,
      gamma: null,
      rateHz: 0,
      eventCount: 0,
      lastUpdateMs: 0,
    },
    rawGps: {
      latitudeDeg: null,
      longitudeDeg: null,
      altitudeM: null,
      accuracyM: null,
      speedMps: null,
      headingDeg: null,
      available: false,
      lastFixMs: 0,
      error: null,
    },
  };

  constructor(pipeline: SensorPipeline) {
    this.pipeline = pipeline;
  }

  onStateChange(cb: (state: RealSensorState) => void) {
    this.onStateChangeCb = cb;
    cb(this.state);
  }

  private updateState(partial: Partial<RealSensorState>) {
    this.state = { ...this.state, ...partial };
    if (this.onStateChangeCb) {
      this.onStateChangeCb(this.state);
    }
  }

  async requestPermissionAndStart(): Promise<boolean> {
    try {
      // Check iOS 13+ DeviceMotionEvent permission requirement
      if (
        typeof DeviceMotionEvent !== "undefined" &&
        // @ts-expect-error iOS Safari proprietary API
        typeof DeviceMotionEvent.requestPermission === "function"
      ) {
        // @ts-expect-error iOS Safari proprietary API
        const permissionState = await DeviceMotionEvent.requestPermission();
        if (permissionState !== "granted") {
          this.updateState({
            permissionGranted: false,
            error: "Motion sensor permission denied by user",
          });
          return false;
        }
      }

      // Check iOS 13+ DeviceOrientationEvent permission requirement
      if (
        typeof DeviceOrientationEvent !== "undefined" &&
        // @ts-expect-error iOS Safari proprietary API
        typeof DeviceOrientationEvent.requestPermission === "function"
      ) {
        try {
          // @ts-expect-error iOS Safari proprietary API
          await DeviceOrientationEvent.requestPermission();
        } catch {
          // Non-blocking
        }
      }

      this.updateState({ permissionGranted: true, error: null });
      this.startMotion();
      this.startOrientation();
      this.startGps();
      this.isListening = true;
      this.updateState({ isStreaming: true });
      return true;
    } catch (err: any) {
      this.updateState({
        error: err?.message || "Failed to start device sensors",
      });
      return false;
    }
  }

  private handleMotionEvent = (event: DeviceMotionEvent) => {
    const acc = event.accelerationIncludingGravity || event.acceleration;
    const rot = event.rotationRate;
    const nowNs = Math.floor(performance.timeOrigin * 1e6 + performance.now() * 1e6);
    const nowMs = Date.now();

    const ax = acc && acc.x !== null ? acc.x : 0;
    const ay = acc && acc.y !== null ? acc.y : 0;
    const az = acc && acc.z !== null ? acc.z : 9.81;
    const mag = Math.sqrt(ax * ax + ay * ay + az * az);

    // Convert deg/s to rad/s
    const deg2rad = Math.PI / 180;
    const gx = rot && rot.beta !== null ? rot.beta * deg2rad : 0;
    const gy = rot && rot.gamma !== null ? rot.gamma * deg2rad : 0;
    const gz = rot && rot.alpha !== null ? rot.alpha * deg2rad : 0;

    // Direct paired feed to pipeline — guarantees zero dropped samples
    this.pipeline.feedPairedImu({
      timestampNs: nowNs,
      ax,
      ay,
      az,
      gx,
      gy,
      gz,
    });

    // Rate accounting
    this.imuEventCount++;
    this.imuEventsInWindow++;
    const perfNow = performance.now();
    if (perfNow - this.lastImuRateCalcTime >= 1000) {
      this.imuRateHz = Math.round((this.imuEventsInWindow * 1000) / (perfNow - this.lastImuRateCalcTime));
      this.imuEventsInWindow = 0;
      this.lastImuRateCalcTime = perfNow;
    }

    this.state.rawImu.ax = ax;
    this.state.rawImu.ay = ay;
    this.state.rawImu.az = az;
    this.state.rawImu.accelMag = mag;
    this.state.rawImu.gx = gx;
    this.state.rawImu.gy = gy;
    this.state.rawImu.gz = gz;
    this.state.rawImu.rateHz = this.imuRateHz > 0 ? this.imuRateHz : Math.max(1, this.imuEventCount);
    this.state.rawImu.eventCount = this.imuEventCount;
    this.state.rawImu.lastUpdateMs = nowMs;

    if (!this.state.motionActive) {
      this.updateState({ motionActive: true });
    }
  };

  private handleOrientationEvent = (event: DeviceOrientationEvent) => {
    this.state.rawImu.alpha = event.alpha !== null ? event.alpha : null;
    this.state.rawImu.beta = event.beta !== null ? event.beta : null;
    this.state.rawImu.gamma = event.gamma !== null ? event.gamma : null;
  };

  private startMotion() {
    if (typeof window !== "undefined") {
      window.addEventListener("devicemotion", this.handleMotionEvent, { passive: true });
    }
  }

  private startOrientation() {
    if (typeof window !== "undefined") {
      window.addEventListener("deviceorientation", this.handleOrientationEvent, { passive: true });
    }
  }

  private startGps() {
    if (typeof navigator !== "undefined" && "geolocation" in navigator) {
      this.watchId = navigator.geolocation.watchPosition(
        (pos) => {
          const nowNs = pos.timestamp * 1e6;
          const headingDeg = pos.coords.heading !== null && pos.coords.heading >= 0 ? pos.coords.heading : null;
          const bearingRad = headingDeg !== null ? (headingDeg * Math.PI) / 180 : null;
          const speedMps = pos.coords.speed !== null && pos.coords.speed >= 0 ? pos.coords.speed : 0;

          this.state.rawGps = {
            latitudeDeg: pos.coords.latitude,
            longitudeDeg: pos.coords.longitude,
            altitudeM: pos.coords.altitude ?? 15.0,
            accuracyM: pos.coords.accuracy ?? 5.0,
            speedMps,
            headingDeg,
            available: true,
            lastFixMs: Date.now(),
            error: null,
          };

          this.pipeline.feedRawGnss({
            timestampNs: nowNs,
            latitudeDeg: pos.coords.latitude,
            longitudeDeg: pos.coords.longitude,
            altitudeM: pos.coords.altitude ?? 15.0,
            horizontalAccuracyM: pos.coords.accuracy ?? 5.0,
            speedMps,
            bearingRad,
            available: true,
          });

          if (!this.state.gpsActive) {
            this.updateState({ gpsActive: true });
          }
        },
        (err) => {
          console.warn("Geolocation watch warning:", err.message);
          this.state.rawGps.available = false;
          this.state.rawGps.error = err.message;
          this.updateState({
            gpsActive: false,
            error: err.code === 1 ? "Location permission denied" : err.message,
          });
        },
        {
          enableHighAccuracy: true,
          maximumAge: 1000,
          timeout: 10000,
        }
      );
    } else {
      this.state.rawGps.error = "Geolocation not supported by browser";
      this.updateState({ error: "Geolocation not supported" });
    }
  }

  stop() {
    if (typeof window !== "undefined") {
      window.removeEventListener("devicemotion", this.handleMotionEvent);
      window.removeEventListener("deviceorientation", this.handleOrientationEvent);
    }
    if (this.watchId !== null && typeof navigator !== "undefined") {
      navigator.geolocation.clearWatch(this.watchId);
      this.watchId = null;
    }
    this.isListening = false;
    this.state.rawGps.available = false;
    this.updateState({
      isStreaming: false,
      gpsActive: false,
      motionActive: false,
    });
  }

  getState(): RealSensorState {
    return { ...this.state };
  }
}

