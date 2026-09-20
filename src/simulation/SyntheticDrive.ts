// Synthetic Drive Generator for Development & Navigation Demonstration
// Produces synchronized 100 Hz IMU (accel + gyro) and 1 Hz GNSS feeds
// Traces realistic road coordinates in Visakhapatnam with defined tunnel zones.

import { GnssSample, ImuSample, Scenario, SyntheticState } from "../types";

// Base route points along Visakhapatnam highway corridor
export const VIZAG_ROUTE_WAYPOINTS = [
  { lat: 17.6868, lon: 83.2185, name: "Siripuram Junction" },
  { lat: 17.6952, lon: 83.2280, name: "Maddilapalem Expressway" },
  { lat: 17.7085, lon: 83.2420, name: "Hanumanthawaka Junction" },
  { lat: 17.7220, lon: 83.2580, name: "Kailasagiri Bypass Entry" },
  { lat: 17.7340, lon: 83.2720, name: "Simhachalam Tunnel Approach" },
  { lat: 17.7420, lon: 83.2810, name: "Simhachalam Tunnel Portal (Entrance)" },
  { lat: 17.7485, lon: 83.2885, name: "Tunnel Midpoint (Zero GNSS)" },
  { lat: 17.7550, lon: 83.2960, name: "Simhachalam Tunnel Exit" },
  { lat: 17.7680, lon: 83.3100, name: "Madhurawada Tech Zone" },
  { lat: 17.7820, lon: 83.3250, name: "Rushikonda Coastal Highway" },
];

export class SyntheticDrive {
  private t0Ms = 0;
  private timerImu: ReturnType<typeof setInterval> | null = null;
  private timerGnss: ReturnType<typeof setInterval> | null = null;
  private state: SyntheticState = {
    scenario: "SIMHACHALAM_TUNNEL",
    gnssEnabled: true,
    running: false,
  };
  private imuCb: ((s: ImuSample) => void) | null = null;
  private gnssCb: ((s: GnssSample) => void) | null = null;

  private currentSpeedMps = 16.67; // 60 km/h
  private currentYawRad = 0.65;    // Heading roughly North-East
  private currentLat = VIZAG_ROUTE_WAYPOINTS[4].lat;
  private currentLon = VIZAG_ROUTE_WAYPOINTS[4].lon;
  private currentAltM = 28.5;
  private routeIndex = 4;
  private inTunnelZone = false;

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

    // 50 Hz IMU tick (20ms interval, fast & smooth for UI and model decimation)
    this.timerImu = setInterval(() => this.tickImu(), 20);
    // 1 Hz GNSS tick
    this.timerGnss = setInterval(() => this.tickGnss(), 1000);
  }

  stop() {
    this.state.running = false;
    if (this.timerImu) clearInterval(this.timerImu);
    if (this.timerGnss) clearInterval(this.timerGnss);
    this.timerImu = null;
    this.timerGnss = null;
  }

  setScenario(s: Scenario) {
    this.state.scenario = s;
    if (s === "GNSS_OUTAGE") {
      this.state.gnssEnabled = false;
    } else {
      this.state.gnssEnabled = true;
    }
    if (s === "SIMHACHALAM_TUNNEL") {
      this.currentLat = VIZAG_ROUTE_WAYPOINTS[4].lat;
      this.currentLon = VIZAG_ROUTE_WAYPOINTS[4].lon;
      this.currentSpeedMps = 16.67;
      this.routeIndex = 4;
    }
  }

  setGnssEnabled(enabled: boolean) {
    this.state.gnssEnabled = enabled;
  }

  getState(): SyntheticState {
    return { ...this.state };
  }

  isInTunnel(): boolean {
    return this.inTunnelZone || !this.state.gnssEnabled;
  }

  private tickImu() {
    const nowNs = Date.now() * 1_000_000;
    const t = (Date.now() - this.t0Ms) / 1000;
    const dt = 0.02; // 20 ms

    let ax = 0; // forward acceleration (m/s²)
    let ay = 0; // lateral acceleration (m/s²)
    const az = 9.81 + (Math.random() - 0.5) * 0.15; // vertical gravity + chassis vibration
    let gx = (Math.random() - 0.5) * 0.01; // roll rate
    let gy = (Math.random() - 0.5) * 0.01; // pitch rate
    let gz = 0; // yaw rate (rad/s)

    // Scenario logic
    switch (this.state.scenario) {
      case "SIMHACHALAM_TUNNEL": {
        // Timeline: 0-8s approach tunnel (GNSS ON), 8-32s inside tunnel (GNSS OUTAGE), 32s+ exit (GNSS ON)
        const cycleT = t % 45;
        if (cycleT >= 8 && cycleT < 32) {
          this.inTunnelZone = true;
          // Steady 55-60 km/h speed with road vibration and slight curvature
          this.currentSpeedMps = 15.5 + Math.sin(cycleT * 0.4) * 1.2;
          gz = 0.035 + (Math.random() - 0.5) * 0.01; // gentle tunnel curve
          ax = (Math.random() - 0.5) * 0.25; // road texture
          ay = this.currentSpeedMps * gz;     // centripetal lateral accel
        } else {
          this.inTunnelZone = false;
          this.currentSpeedMps = 16.67;
          gz = (Math.random() - 0.5) * 0.02;
          ax = (Math.random() - 0.5) * 0.15;
        }
        break;
      }

      case "CONSTANT_50KMH":
        this.inTunnelZone = false;
        this.currentSpeedMps = 13.88; // 50 km/h
        ax = (Math.random() - 0.5) * 0.12;
        gz = (Math.random() - 0.5) * 0.015;
        break;

      case "BRAKING_IN_TUNNEL": {
        this.inTunnelZone = true;
        // Starts at 70 km/h, brakes hard to 0
        const brakeT = t % 20;
        if (brakeT < 8) {
          this.currentSpeedMps = Math.max(0, 19.4 - brakeT * 2.4); // deceleration
          ax = -2.4 + (Math.random() - 0.5) * 0.2;
          gy = -0.04; // nose dip on braking
        } else {
          this.currentSpeedMps = 0;
          ax = (Math.random() - 0.5) * 0.02;
        }
        break;
      }

      case "STOP_AND_GO": {
        const sgT = t % 24;
        if (sgT < 8) {
          // Accelerating to 40 km/h
          this.currentSpeedMps = Math.min(11.1, sgT * 1.4);
          ax = 1.4;
        } else if (sgT < 14) {
          // Cruising
          this.currentSpeedMps = 11.1;
          ax = (Math.random() - 0.5) * 0.1;
        } else if (sgT < 18) {
          // Braking to stop
          this.currentSpeedMps = Math.max(0, 11.1 - (sgT - 14) * 2.8);
          ax = -2.8;
        } else {
          // Stationary at light / traffic
          this.currentSpeedMps = 0;
          ax = 0;
        }
        break;
      }

      case "URBAN_CANYON":
        this.inTunnelZone = false;
        this.currentSpeedMps = 11.1; // 40 km/h
        ax = (Math.random() - 0.5) * 0.3;
        gz = Math.sin(t * 0.3) * 0.08;
        break;

      case "TURN":
        this.inTunnelZone = false;
        this.currentSpeedMps = 11.11;
        gz = 0.25; // 0.25 rad/s turn
        ay = this.currentSpeedMps * gz;
        ax = 0.1;
        break;

      case "ACCELERATION":
        this.inTunnelZone = false;
        this.currentSpeedMps = Math.min(28, 8 + (t % 20) * 1.2);
        ax = 1.2;
        break;

      case "GNSS_OUTAGE":
        this.inTunnelZone = true;
        this.currentSpeedMps = 14.5;
        ax = (Math.random() - 0.5) * 0.18;
        gz = 0.02;
        break;

      case "NOISY_IMU":
        this.inTunnelZone = false;
        this.currentSpeedMps = 13.0 + (Math.random() - 0.5) * 1.5;
        ax = (Math.random() - 0.5) * 1.5; // High vibration
        ay = (Math.random() - 0.5) * 1.5;
        gx = (Math.random() - 0.5) * 0.1;
        gy = (Math.random() - 0.5) * 0.1;
        gz = (Math.random() - 0.5) * 0.1;
        break;
    }

    // Integrate heading and positions
    this.currentYawRad += gz * dt;
    this.currentYawRad = Math.atan2(Math.sin(this.currentYawRad), Math.cos(this.currentYawRad));

    const vNorth = this.currentSpeedMps * Math.cos(this.currentYawRad);
    const vEast = this.currentSpeedMps * Math.sin(this.currentYawRad);

    const dNorth = vNorth * dt;
    const dEast = vEast * dt;
    const cosLat = Math.max(0.01, Math.cos((this.currentLat * Math.PI) / 180));

    this.currentLat += dNorth / 111320;
    this.currentLon += dEast / (111320 * cosLat);

    if (this.imuCb) {
      this.imuCb({
        timestampNs: nowNs,
        ax,
        ay,
        az,
        gx,
        gy,
        gz,
      });
    }
  }

  private tickGnss() {
    if (!this.gnssCb) return;

    const nowNs = Date.now() * 1_000_000;
    const isOutage = !this.state.gnssEnabled || this.inTunnelZone;

    if (isOutage) {
      // GNSS is denied inside tunnel or when manually disabled
      this.gnssCb({
        timestampNs: nowNs,
        latitudeDeg: this.currentLat,
        longitudeDeg: this.currentLon,
        altitudeM: this.currentAltM,
        speedMps: this.currentSpeedMps,
        bearingRad: this.currentYawRad,
        horizontalAccuracyM: 99.0, // Denied
        available: false,
      });
    } else {
      // Degraded accuracy in urban canyon scenario
      const isDegraded = this.state.scenario === "URBAN_CANYON";
      const horizAcc = isDegraded ? 22.0 + Math.random() * 12 : 3.2 + Math.random() * 1.5;

      this.gnssCb({
        timestampNs: nowNs,
        latitudeDeg: this.currentLat,
        longitudeDeg: this.currentLon,
        altitudeM: this.currentAltM,
        speedMps: this.currentSpeedMps,
        bearingRad: this.currentYawRad,
        horizontalAccuracyM: horizAcc,
        available: true,
      });
    }
  }
}

export const syntheticDrive = new SyntheticDrive();
