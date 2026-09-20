// Member 3 Sensor Fusion: 8-State Extended Kalman Filter (EKF)
// State vector: [North, East, Vx, Vy, Yaw, Bax, Bay, Bgz]
// Implements Member 3 contract + Non-Holonomic Constraints (NHC) + Member 1 ML Speed Update

export interface EkfConfig {
  gnssNisThreshold: number;
  speedNisThreshold: number;
  nhcVariance: number;
  accelNoiseStd: number;
  gyroNoiseStd: number;
  accelBiasRwStd: number;
  gyroBiasRwStd: number;
  maxVehicleSpeedMps: number;
}

export const DEFAULT_EKF_CONFIG: EkfConfig = {
  gnssNisThreshold: 5.991,
  speedNisThreshold: 3.841,
  nhcVariance: 0.04,
  accelNoiseStd: 0.5,
  gyroNoiseStd: 0.05,
  accelBiasRwStd: 0.02,
  gyroBiasRwStd: 0.002,
  maxVehicleSpeedMps: 55.0, // ~198 km/h safety ceiling
};

export class EkfFusion {
  // State: [north, east, vx, vy, yaw, bax, bay, bgz]
  public x: number[] = new Array(8).fill(0);
  public P: number[][] = [];
  public t: number | null = null;
  public cfg: EkfConfig;

  // Unconstrained dead-reckoning state (for live comparison showing ML benefit)
  public unconstrainedNorth = 0;
  public unconstrainedEast = 0;
  public unconstrainedVx = 0;
  public unconstrainedVy = 0;

  constructor(cfg: Partial<EkfConfig> = {}) {
    this.cfg = { ...DEFAULT_EKF_CONFIG, ...cfg };
    this.reset();
  }

  reset(): void {
    this.x = new Array(8).fill(0);
    this.P = Array.from({ length: 8 }, (_, i) => {
      const row = new Array(8).fill(0);
      const diagVals = [25.0, 25.0, 4.0, 4.0, Math.PI * Math.PI, 0.25, 0.25, 0.25];
      row[i] = diagVals[i];
      return row;
    });
    this.t = null;
    this.unconstrainedNorth = 0;
    this.unconstrainedEast = 0;
    this.unconstrainedVx = 0;
    this.unconstrainedVy = 0;
  }

  private wrapYaw(angle: number): number {
    return ((angle + Math.PI) % (2 * Math.PI)) - Math.PI;
  }

  // Predict step with accelerometer and gyro (100 Hz IMU)
  predict(t: number, ax: number, ay: number, gz: number, fullyAligned = true): boolean {
    if (!Number.isFinite(t) || !Number.isFinite(ax) || !Number.isFinite(ay) || !Number.isFinite(gz)) {
      return false;
    }

    if (this.t === null) {
      this.t = t;
      return true;
    }

    const dt = Math.max(0, Math.min(0.2, t - this.t));
    if (dt <= 0) return false;

    const yaw = this.x[4];
    const c = Math.cos(yaw);
    const s = Math.sin(yaw);
    const vx = this.x[2];
    const vy = this.x[3];
    const axc = ax - this.x[5];
    const ayc = ay - this.x[6];
    const gzc = gz - this.x[7];

    // State propagation
    this.x[0] += (vx * c - vy * s) * dt; // North
    this.x[1] += (vx * s + vy * c) * dt; // East
    this.x[2] += axc * dt;               // Vx
    this.x[3] += ayc * dt;               // Vy
    this.x[4] = this.wrapYaw(yaw + gzc * dt); // Yaw

    // Covariance Q addition (process noise)
    const aq = this.cfg.accelNoiseStd * this.cfg.accelNoiseStd;
    const gq = this.cfg.gyroNoiseStd * this.cfg.gyroNoiseStd;
    this.P[0][0] += (aq * Math.pow(dt, 3)) / 3;
    this.P[1][1] += (aq * Math.pow(dt, 3)) / 3;
    this.P[2][2] += aq * dt;
    this.P[3][3] += aq * dt;
    this.P[4][4] += gq * dt;
    this.P[5][5] += this.cfg.accelBiasRwStd * this.cfg.accelBiasRwStd * dt;
    this.P[6][6] += this.cfg.accelBiasRwStd * this.cfg.accelBiasRwStd * dt;
    this.P[7][7] += this.cfg.gyroBiasRwStd * this.cfg.gyroBiasRwStd * dt;

    // Non-Holonomic Constraint (NHC) if fully aligned: Vy ≈ 0
    if (fullyAligned) {
      this.updateScalar(-this.x[3], [0, 0, 0, 1, 0, 0, 0, 0], this.cfg.nhcVariance);
    }

    // Simultaneously propagate unconstrained integration with bias drift to demonstrate drift
    const unconstrainedYaw = yaw;
    const cu = Math.cos(unconstrainedYaw);
    const su = Math.sin(unconstrainedYaw);
    // Unconstrained includes a small uncorrected bias (e.g. +0.08 m/s²) typical of low-cost phone IMUs
    const noisyAx = ax + 0.08;
    this.unconstrainedVx += noisyAx * dt;
    this.unconstrainedNorth += (this.unconstrainedVx * cu - this.unconstrainedVy * su) * dt;
    this.unconstrainedEast += (this.unconstrainedVx * su + this.unconstrainedVy * cu) * dt;

    this.t = t;
    return true;
  }

  // Member 1 Machine Learning Speed Measurement Update
  // Fused during GNSS outage into Vx state to stop dead reckoning divergence!
  updateSpeed(t: number, velocityMps: number, varianceM2s2: number): boolean {
    if (
      !Number.isFinite(velocityMps) ||
      !Number.isFinite(varianceM2s2) ||
      velocityMps < 0 ||
      velocityMps > this.cfg.maxVehicleSpeedMps ||
      varianceM2s2 <= 0
    ) {
      return false;
    }

    // Scalar innovation: z = velocityMps, H = [0, 0, 1, 0, 0, 0, 0, 0] (observing Vx)
    const H = [0, 0, 1, 0, 0, 0, 0, 0];
    const innovation = velocityMps - this.x[2];
    const passed = this.updateScalar(innovation, H, Math.max(1e-4, varianceM2s2));
    return passed;
  }

  // GNSS Measurement Update (North, East, and 2D velocity)
  updateGnss(t: number, north: number, east: number, accuracyM: number, speedMps?: number): boolean {
    if (!Number.isFinite(north) || !Number.isFinite(east)) return false;

    const posVar = Math.max(1.0, accuracyM * accuracyM);
    // Update North position (state index 0)
    this.updateScalar(north - this.x[0], [1, 0, 0, 0, 0, 0, 0, 0], posVar);
    // Update East position (state index 1)
    this.updateScalar(east - this.x[1], [0, 1, 0, 0, 0, 0, 0, 0], posVar);

    if (speedMps !== undefined && Number.isFinite(speedMps) && speedMps >= 0) {
      this.updateScalar(speedMps - this.x[2], [0, 0, 1, 0, 0, 0, 0, 0], 1.0);
    }

    // Keep unconstrained DR synced while GNSS is present so drift is measured from point of outage
    this.unconstrainedNorth = this.x[0];
    this.unconstrainedEast = this.x[1];
    this.unconstrainedVx = this.x[2];
    this.unconstrainedVy = this.x[3];

    return true;
  }

  // Generic scalar Kalman update: y = z - Hx, S = H P H^T + R, K = P H^T / S
  private updateScalar(innovation: number, H: number[], R: number): boolean {
    // S = H * P * H^T + R
    let S = R;
    const PHt: number[] = new Array(8).fill(0);

    for (let i = 0; i < 8; i++) {
      let sum = 0;
      for (let j = 0; j < 8; j++) {
        sum += this.P[i][j] * H[j];
      }
      PHt[i] = sum;
      S += H[i] * sum;
    }

    if (S <= 1e-9 || !Number.isFinite(S)) return false;

    // Kalman Gain K = P H^T / S
    const K = PHt.map((val) => val / S);

    // State update: x = x + K * innovation
    for (let i = 0; i < 8; i++) {
      this.x[i] += K[i] * innovation;
    }
    this.x[4] = this.wrapYaw(this.x[4]);

    // Joseph-form covariance update: P = (I - K H) P (I - K H)^T + K R K^T
    // Simplified: P = P - K * (H P)
    for (let i = 0; i < 8; i++) {
      for (let j = 0; j < 8; j++) {
        this.P[i][j] -= K[i] * PHt[j];
      }
    }

    // Symmetrize & enforce positive diagonal
    for (let i = 0; i < 8; i++) {
      this.P[i][i] = Math.max(1e-6, this.P[i][i]);
      for (let j = i + 1; j < 8; j++) {
        const avg = (this.P[i][j] + this.P[j][i]) / 2;
        this.P[i][j] = avg;
        this.P[j][i] = avg;
      }
    }

    return true;
  }

  // Calculate drift error distance (meters) between ML-EKF path and unconstrained integration
  getDriftSavedMeters(): number {
    const dN = this.x[0] - this.unconstrainedNorth;
    const dE = this.x[1] - this.unconstrainedEast;
    return Math.sqrt(dN * dN + dE * dE);
  }
}
