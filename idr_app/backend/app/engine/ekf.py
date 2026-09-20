from __future__ import annotations

import math

import numpy as np

from .geo import MAX_VEHICLE_SPEED_MPS, LocalTangent, heading_from_east_ccw_rad, wrap_angle
from .types import AlignedImu, GnssSample, NavMode, NavigationState, SpeedEstimate


class EkfFusion:
    """8-state vehicle EKF: [x, y, vx, vy, yaw, bax, bay, bgz]."""

    def __init__(self, origin: LocalTangent) -> None:
        self.origin = origin
        self.x = np.zeros(8)
        self.P = np.diag([25, 25, 4, 4, 0.3, 0.2, 0.2, 0.05])
        self.initialized = False
        self.mode = NavMode.INIT
        self._last_t: float | None = None
        self.Q = np.diag([0.05, 0.05, 0.4, 0.4, 0.02, 1e-4, 1e-4, 5e-5])

    def reset(self, origin: LocalTangent | None = None) -> None:
        if origin is not None:
            self.origin = origin
        self.__init__(self.origin)

    def initialize_from_gnss(self, gnss: GnssSample, yaw: float) -> None:
        x, y = self.origin.to_xy(gnss.lat, gnss.lon)
        self.x[0], self.x[1] = x, y
        spd = max(0.0, gnss.speed)
        self.x[2] = spd * math.cos(yaw)
        self.x[3] = spd * math.sin(yaw)
        self.x[4] = yaw
        self.initialized = True
        self._last_t = gnss.timestamp
        self.mode = NavMode.GNSS

    def predict(self, imu: AlignedImu) -> None:
        if not self.initialized:
            return
        if self._last_t is None:
            self._last_t = imu.timestamp
            return
        dt = imu.timestamp - self._last_t
        if dt <= 0 or dt > 0.5:
            self._last_t = imu.timestamp
            return
        self._last_t = imu.timestamp
        x, y, vx, vy, yaw, bax, bay, bgz = self.x
        ax = imu.ax_v - bax
        ay = imu.ay_v - bay
        gz = imu.gz_v - bgz
        c, s = math.cos(yaw), math.sin(yaw)
        ax_e = ax * c - ay * s
        ay_n = ax * s + ay * c
        vx_n = vx + ax_e * dt
        vy_n = vy + ay_n * dt
        x_n = x + vx * dt + 0.5 * ax_e * dt * dt
        y_n = y + vy * dt + 0.5 * ay_n * dt * dt
        yaw_n = wrap_angle(yaw + gz * dt)
        self.x = np.array([x_n, y_n, vx_n, vy_n, yaw_n, bax, bay, bgz])

        F = np.eye(8)
        F[0, 2] = dt
        F[1, 3] = dt
        F[0, 4] = (-ax * s - ay * c) * 0.5 * dt * dt
        F[1, 4] = (ax * c - ay * s) * 0.5 * dt * dt
        F[2, 4] = (-ax * s - ay * c) * dt
        F[3, 4] = (ax * c - ay * s) * dt
        F[2, 5] = -c * dt
        F[2, 6] = s * dt
        F[3, 5] = -s * dt
        F[3, 6] = -c * dt
        F[4, 7] = -dt
        self.P = F @ self.P @ F.T + self.Q * dt

    def _update(self, z: np.ndarray, H: np.ndarray, R: np.ndarray, gate: float) -> bool:
        y = z - H @ self.x
        if H.shape[0] >= 1 and H.shape[1] > 4:
            # wrap yaw residual if measuring yaw
            pass
        S = H @ self.P @ H.T + R
        try:
            nis = float(y.T @ np.linalg.solve(S, y))
        except np.linalg.LinAlgError:
            return False
        dof = z.shape[0]
        if nis > gate * dof:
            return False
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.x[4] = wrap_angle(float(self.x[4]))
        I = np.eye(8)
        self.P = (I - K @ H) @ self.P
        self.P = 0.5 * (self.P + self.P.T)
        return True

    def update_gnss(self, gnss: GnssSample, degraded: bool = False) -> bool:
        if not gnss.valid or not self.initialized:
            return False
        px, py = self.origin.to_xy(gnss.lat, gnss.lon)
        scale = 8.0 if degraded else 1.0
        z = np.array([px, py, max(0.0, gnss.speed)])
        H = np.zeros((3, 8))
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        spd = math.hypot(self.x[2], self.x[3]) + 1e-6
        H[2, 2] = self.x[2] / spd
        H[2, 3] = self.x[3] / spd
        R = np.diag([4.0 * scale, 4.0 * scale, 0.8 * scale])
        ok = self._update(z, H, R, gate=13.0)
        if ok:
            self.mode = NavMode.GNSS_DEGRADED if degraded else NavMode.GNSS
        return ok

    def update_ai_speed(self, est: SpeedEstimate) -> bool:
        if not est.valid or not self.initialized:
            return False
        if est.velocity_mps > MAX_VEHICLE_SPEED_MPS:
            return False
        yaw = float(self.x[4])
        c, s = math.cos(yaw), math.sin(yaw)
        H = np.zeros((1, 8))
        H[0, 2] = c
        H[0, 3] = s
        z = np.array([est.velocity_mps])
        R = np.array([[max(0.25, est.variance)]])
        return self._update(z, H, R, gate=9.0)

    def update_nhc(self) -> bool:
        if not self.initialized:
            return False
        yaw = float(self.x[4])
        # body lateral velocity ≈ 0: -vx sin + vy cos
        H = np.zeros((1, 8))
        H[0, 2] = -math.sin(yaw)
        H[0, 3] = math.cos(yaw)
        z = np.array([0.0])
        R = np.array([[0.15]])
        return self._update(z, H, R, gate=8.0)

    def update_vision_delta(self, dx: float, dy: float, var: float) -> bool:
        if not self.initialized:
            return False
        H = np.zeros((2, 8))
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        z = np.array([self.x[0] + dx, self.x[1] + dy])
        R = np.diag([var, var])
        ok = self._update(z, H, R, gate=10.0)
        if ok:
            self.mode = NavMode.VISION_AIDED
        return ok

    def update_v2x(self, lat: float, lon: float, var: float) -> bool:
        if not self.initialized:
            return False
        px, py = self.origin.to_xy(lat, lon)
        H = np.zeros((2, 8))
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        z = np.array([px, py])
        R = np.diag([var, var])
        return self._update(z, H, R, gate=12.0)

    def set_dead_reckoning(self) -> None:
        if self.mode != NavMode.VISION_AIDED:
            self.mode = NavMode.DEAD_RECKONING

    def state(self, timestamp: float, speed_valid: bool) -> NavigationState:
        lat, lon = self.origin.to_ll(float(self.x[0]), float(self.x[1]))
        spd = math.hypot(float(self.x[2]), float(self.x[3]))
        if not math.isfinite(spd) or spd > MAX_VEHICLE_SPEED_MPS:
            spd = 0.0
            speed_valid = False
        std = math.sqrt(max(0.0, float(self.P[0, 0] + self.P[1, 1])))
        return NavigationState(
            timestamp=timestamp,
            x=float(self.x[0]),
            y=float(self.x[1]),
            vx=float(self.x[2]),
            vy=float(self.x[3]),
            yaw=float(self.x[4]),
            bax=float(self.x[5]),
            bay=float(self.x[6]),
            bgz=float(self.x[7]),
            lat=lat,
            lon=lon,
            heading_deg=heading_from_east_ccw_rad(float(self.x[4])),
            speed_mps=spd,
            speed_valid=speed_valid and math.isfinite(spd),
            mode=self.mode,
            pos_std_m=std,
            P_diag=[float(self.P[i, i]) for i in range(8)],
        )
