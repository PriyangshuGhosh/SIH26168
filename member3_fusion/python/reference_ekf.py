"""NumPy reference for Member 3's 8-state EKF contract.

State: [north, east, vx, vy, yaw, bax, bay, bgz].
The reference mirrors the production prediction model, NHC, scalar speed
update, timestamp policy, and NIS thresholds without depending on C++ code.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass
class Config:
    gnss_nis_threshold: float = 5.991
    speed_nis_threshold: float = 3.841
    nhc_nis_threshold: float = 3.841
    nhc_variance: float = 0.04
    max_measurement_age_s: float = 0.10
    max_measurement_lead_s: float = 0.0
    max_prediction_dt_s: float = 0.10
    max_gap_s: float = 1.0
    accel_noise_std: float = 0.5
    gyro_noise_std: float = 0.05
    accel_bias_rw_std: float = 0.02
    gyro_bias_rw_std: float = 0.002
    degraded_process_scale: float = 4.0


class EKFReference:
    """State [north,east,vx,vy,yaw,bax,bay,bgz]; SI units and radians."""

    def __init__(self, config=None):
        self.cfg = config or Config()
        self.reset()

    def reset(self):
        self.x = np.zeros(8)
        self.P = np.diag([25.0, 25.0, 4.0, 4.0, math.pi**2, 0.25, 0.25, 0.25])
        self.t = None
        self.ref = None

    @staticmethod
    def _yaw(a):
        return (a + math.pi) % (2 * math.pi) - math.pi

    def _stabilize(self):
        self.P = (self.P + self.P.T) * 0.5
        if not np.isfinite(self.P).all():
            return False
        values, vectors = np.linalg.eigh(self.P)
        if values.min() < 0.0:
            values = np.maximum(values, 1e-9)
            self.P = vectors @ np.diag(values) @ vectors.T
        self.P = (self.P + self.P.T) * 0.5
        self.P[np.diag_indices(8)] = np.maximum(np.diag(self.P), 1e-9)
        return np.isfinite(self.P).all()

    def _time_valid(self, t):
        if not np.isfinite(t):
            return False
        if self.t is None:
            return True
        return (t <= self.t + self.cfg.max_measurement_lead_s and
                t >= self.t - self.cfg.max_measurement_age_s)

    def _scalar(self, innovation, H, variance, threshold):
        S = float(H @ self.P @ H.T + variance)
        if not np.isfinite(S) or S <= 1e-9:
            return False
        nis = innovation * innovation / S
        if not np.isfinite(nis) or nis > threshold:
            return False
        K = self.P @ H.T / S
        A = np.eye(8) - K @ H
        self.x += K[:, 0] * innovation
        self.P = A @ self.P @ A.T + K * variance @ K.T
        self.x[4] = self._yaw(self.x[4])
        return self._stabilize() and np.isfinite(self.x).all()

    def predict(self, t, ax, ay, gz, fully_aligned=True):
        if not np.isfinite([t, ax, ay, gz]).all():
            return False
        if self.t is None:
            self.t = float(t)
            return True
        raw = float(t) - self.t
        if not np.isfinite(raw) or raw <= 0.0:
            return False
        if raw > self.cfg.max_gap_s:
            aq = self.cfg.accel_noise_std**2
            gq = self.cfg.gyro_noise_std**2
            gap = max(raw, 1.0)
            self.P[0, 0] += aq * gap**3 / 3.0
            self.P[1, 1] += aq * gap**3 / 3.0
            self.P[2, 2] += aq * gap
            self.P[3, 3] += aq * gap
            self.P[4, 4] += gq * gap
            self.t = float(t)
            return self._stabilize()

        remaining = raw
        while remaining > 0.0:
            dt = min(remaining, self.cfg.max_prediction_dt_s)
            yaw = self.x[4]
            c, s = math.cos(yaw), math.sin(yaw)
            vx, vy = self.x[2:4]
            axc = ax - self.x[5]
            ayc = ay - self.x[6]
            gzc = gz - self.x[7]

            self.x[0] += (vx * c - vy * s) * dt
            self.x[1] += (vx * s + vy * c) * dt
            self.x[2] += axc * dt
            self.x[3] += ayc * dt
            self.x[4] = self._yaw(yaw + gzc * dt)

            F = np.eye(8)
            F[0, 2], F[0, 3] = c * dt, -s * dt
            F[1, 2], F[1, 3] = s * dt, c * dt
            F[0, 4] = (-vx * s - vy * c) * dt
            F[1, 4] = (vx * c - vy * s) * dt
            F[2, 5], F[3, 6], F[4, 7] = -dt, -dt, -dt

            scale = 1.0 if fully_aligned else self.cfg.degraded_process_scale
            aq = scale * self.cfg.accel_noise_std**2
            gq = scale * self.cfg.gyro_noise_std**2
            dt2 = dt * dt
            dt3 = dt2 * dt
            Q = np.zeros((8, 8))
            Q[0, 0] = Q[1, 1] = aq * dt3 / 3.0
            Q[0, 2] = Q[2, 0] = aq * dt2 / 2.0
            Q[1, 3] = Q[3, 1] = aq * dt2 / 2.0
            Q[2, 2] = Q[3, 3] = aq * dt
            Q[4, 4] = gq * dt
            Q[5, 5] = Q[6, 6] = self.cfg.accel_bias_rw_std**2 * dt
            Q[7, 7] = self.cfg.gyro_bias_rw_std**2 * dt
            self.P = F @ self.P @ F.T + Q
            remaining -= dt

        if fully_aligned:
            H = np.zeros((1, 8))
            H[0, 3] = 1.0
            self._scalar(-self.x[3], H, self.cfg.nhc_variance,
                         self.cfg.nhc_nis_threshold)
        self.t = float(t)
        return self._stabilize() and np.isfinite(self.x).all()

    def update_speed(self, t, velocity, variance):
        if not self._time_valid(t):
            return False
        if (not np.isfinite([t, velocity, variance]).all() or
                velocity < 0.0 or velocity > 100.0 or variance <= 0.0):
            return False
        H = np.zeros((1, 8))
        H[0, 2] = 1.0
        return self._scalar(velocity - self.x[2], H, max(variance, 1e-4),
                            self.cfg.speed_nis_threshold)


if __name__ == "__main__":
    ref = EKFReference()
    assert ref.predict(0.0, 0.0, 0.0, 0.0)
    assert ref.predict(0.25, 1.0, 0.0, 0.0)
    assert abs(ref.x[2] - 0.25) < 0.02
    assert ref.update_speed(0.25, 0.25, 0.25)
    print("NumPy Member 3 EKF reference smoke test passed.")
