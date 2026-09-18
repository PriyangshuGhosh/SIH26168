"""Streaming phone→vehicle IMU frame aligner (Python reference)."""

from __future__ import annotations

from collections import deque
import math

import numpy as np

from .frames import (
    is_finite_vec,
    phoneToVehicleVector,
    quatPhoneToVehicle,
    quat_identity,
    rotation_gravity_up_to_vehicle_z,
    rotation_z,
    safe_normalize,
    vector_norm,
)
from .types import (
    AlignedIMUFrame,
    CalibrationConfidence,
    CalibrationStatus,
    FrameAlignerConfig,
    OptionalGnssAid,
)


class FrameAligner:
    """Online aligner: ``feed(raw IMU) → AlignedIMUFrame``.

    Thread-safety: not internally synchronized. Serialize ``process`` / ``feed_gnss``.
    Memory: bounded deques sized from configuration; no per-call heap growth.
    """

    def __init__(self, config: FrameAlignerConfig | None = None) -> None:
        self.cfg = config or FrameAlignerConfig()
        self.reset()

    def reset(self) -> None:
        n = int(self.cfg.static_window_samples)
        self._acc_hist: deque[np.ndarray] = deque(maxlen=n)
        self._gyro_hist: deque[np.ndarray] = deque(maxlen=n)
        self._t_hist: deque[float] = deque(maxlen=n)
        self._valid_hist: deque[bool] = deque(maxlen=max(n, 100))

        self._have_time = False
        self._t_prev = 0.0
        self._t_last_valid = 0.0

        self._status = CalibrationStatus.UNINITIALIZED
        self._g_up_p: np.ndarray | None = None
        self._g_initialized = False
        self._yaw: float | None = None
        self._yaw_axis: np.ndarray | None = None
        self._R_vp = np.eye(3)
        self._q_pv = quat_identity()

        self._scatter = np.zeros((2, 2))
        self._signed_sum = np.zeros(2)
        self._axis_evidence = 0.0
        self._turn_evidence = 0.0
        self._gnss_sign_evidence = 0.0
        self._last_yaw_update_t: float | None = None
        self._last_static_t: float | None = None
        self._last_gravity_update_t: float | None = None

        self._gnss: OptionalGnssAid | None = None
        self._gnss_speed_prev: float | None = None
        self._gnss_t_prev: float | None = None
        self._gnss_accel = 0.0

        self._sensor_quality = 1.0
        self._gravity_conf = 0.0
        self._yaw_conf = 0.0
        self._temporal_conf = 0.0

        self._static_streak_s = 0.0
        self._last_good_frame: AlignedIMUFrame | None = None

    def status(self) -> CalibrationStatus:
        return self._status

    def confidence(self) -> CalibrationConfidence:
        return self._compose_confidence()

    def rotationMatrixPhoneToVehicle(self) -> np.ndarray:
        return self._R_vp.copy()

    def quatPhoneToVehicle(self) -> np.ndarray:
        return self._q_pv.copy()

    def feed_gnss(self, aid: OptionalGnssAid) -> None:
        """Optional calibration evidence only. Runtime alignment does not require GNSS."""
        self._gnss = aid
        if self._gnss_t_prev is not None:
            dt = aid.timestamp - self._gnss_t_prev
            if 0.005 <= dt <= 1.0:
                raw = (aid.speed_mps - float(self._gnss_speed_prev)) / dt
                if np.isfinite(raw) and abs(raw) <= self.cfg.gnss_max_abs_accel:
                    self._gnss_accel = 0.3 * raw + 0.7 * self._gnss_accel
        self._gnss_speed_prev = aid.speed_mps
        self._gnss_t_prev = aid.timestamp

    def process(
        self,
        timestamp: float,
        ax_p: float,
        ay_p: float,
        az_p: float,
        gx_p: float,
        gy_p: float,
        gz_p: float,
    ) -> AlignedIMUFrame:
        acc = np.array([ax_p, ay_p, az_p], dtype=float)
        gyro = np.array([gx_p, gy_p, gz_p], dtype=float)
        return self._process_sample(timestamp, acc, gyro)

    def _process_sample(
        self, t: float, acc: np.ndarray, gyro: np.ndarray
    ) -> AlignedIMUFrame:
        ok, reason_invalid, dt, gap = self._validate(t, acc, gyro)
        self._valid_hist.append(ok)
        self._sensor_quality = float(np.mean(self._valid_hist)) if self._valid_hist else 0.0

        if not ok:
            # Reject this sample only; keep last committed alignment status.
            return self._emit(t, acc, gyro, force_status=CalibrationStatus.INVALID)

        if gap:
            self._acc_hist.clear()
            self._gyro_hist.clear()
            self._t_hist.clear()
            self._static_streak_s = 0.0
            if self._status in (
                CalibrationStatus.FULLY_ALIGNED,
                CalibrationStatus.YAW_UNCERTAIN,
                CalibrationStatus.ROLL_PITCH_VALID,
            ):
                self._status = CalibrationStatus.DEGRADED

        self._acc_hist.append(acc)
        self._gyro_hist.append(gyro)
        self._t_hist.append(t)

        static = self._is_quasi_static()
        if static:
            self._static_streak_s += dt if dt > 0 else self.cfg.nominal_dt()
            self._last_static_t = t
            if self._status == CalibrationStatus.UNINITIALIZED:
                self._status = CalibrationStatus.STATIC_DETECTED
            self._update_gravity(acc, t)
        else:
            self._static_streak_s = 0.0
            self._check_phone_moved(acc, t)

        if self._g_initialized:
            self._update_yaw(t, acc, gyro, dt if dt > 0 else self.cfg.nominal_dt())

        self._refresh_status(t)
        self._rebuild_rotation()
        return self._emit(t, acc, gyro)

    def _validate(
        self, t: float, acc: np.ndarray, gyro: np.ndarray
    ) -> tuple[bool, bool, float, bool]:
        if not np.isfinite(t) or not is_finite_vec(acc) or not is_finite_vec(gyro):
            return False, True, 0.0, False
        if vector_norm(acc) > self.cfg.max_accel_norm or vector_norm(gyro) > self.cfg.max_gyro_norm:
            return False, True, 0.0, False
        if not self._have_time:
            self._have_time = True
            self._t_prev = t
            self._t_last_valid = t
            return True, False, 0.0, False
        dt = t - self._t_prev
        if dt < 0.0:
            return False, True, 0.0, False
        if dt < self.cfg.min_dt_s:
            # duplicate / sub-resolution timestamp: ignore update
            return False, False, 0.0, False
        gap = dt > self.cfg.gap_reset_s
        self._t_prev = t
        self._t_last_valid = t
        return True, False, dt, gap

    def _is_quasi_static(self) -> bool:
        n = len(self._acc_hist)
        if n < max(5, int(0.5 * self.cfg.static_window_samples)):
            return False
        acc = np.stack(self._acc_hist, axis=0)
        gyro = np.stack(self._gyro_hist, axis=0)
        g = self.cfg.gravity_mps2
        norms = np.linalg.norm(acc, axis=1)
        if np.max(np.abs(norms - g)) > self.cfg.static_accel_norm_tol:
            return False
        if np.max(np.linalg.norm(gyro, axis=1)) > self.cfg.static_gyro_norm_max:
            return False
        if np.max(np.var(acc, axis=0)) > self.cfg.static_accel_var_max:
            return False
        if self._g_initialized and self._g_up_p is not None:
            ghat = self._g_up_p
            min_dot = float(np.cos(self.cfg.static_dir_align_rad))
            for row in acc:
                an = safe_normalize(row)
                if vector_norm(an) < 1e-9 or float(np.dot(an, ghat)) < min_dot:
                    return False
        if self._t_hist[-1] - self._t_hist[0] < 0.5 * self.cfg.min_static_duration_s:
            return False
        return self._static_streak_s + self.cfg.nominal_dt() >= 0.5 * self.cfg.min_static_duration_s or n >= self.cfg.static_window_samples

    def _update_gravity(self, acc: np.ndarray, t: float) -> None:
        if self._static_streak_s < self.cfg.min_static_duration_s and not self._g_initialized:
            if len(self._acc_hist) < self.cfg.static_window_samples:
                return
        if not self._g_initialized:
            self._g_up_p = safe_normalize(np.mean(np.stack(self._acc_hist), axis=0))
            if vector_norm(self._g_up_p) < 1e-9:
                self._g_up_p = None
                return
            self._g_initialized = True
            self._gravity_conf = 0.4
        else:
            prev = self._g_up_p
            ema = (1.0 - self.cfg.gravity_ema_alpha) * prev + self.cfg.gravity_ema_alpha * acc
            nxt = safe_normalize(ema)
            if vector_norm(nxt) < 1e-9:
                return
            dot = float(np.clip(np.dot(prev, nxt), -1.0, 1.0))
            ang = float(np.arccos(dot))
            if ang > self.cfg.gravity_max_tilt_jump_rad:
                self._status = CalibrationStatus.REINITIALIZING
                self._clear_yaw()
                self._g_up_p = nxt
            else:
                self._g_up_p = nxt
            self._gravity_conf = float(np.clip(self._gravity_conf * 0.98 + 0.02 * (1.0 - ang / 0.5), 0.0, 1.0))
        self._last_gravity_update_t = t
        if self._status in (
            CalibrationStatus.UNINITIALIZED,
            CalibrationStatus.STATIC_DETECTED,
            CalibrationStatus.REINITIALIZING,
        ):
            self._status = CalibrationStatus.ROLL_PITCH_VALID

    def _check_phone_moved(self, acc: np.ndarray, t: float) -> None:
        if not self._g_initialized or self._g_up_p is None:
            return
        # If the specific-force direction drifts far from estimated up while
        # gyro is large, the phone is likely being handled — not vehicle motion.
        an = vector_norm(acc)
        if an < 1.0:
            return
        up_meas = acc / an
        dot = float(np.clip(np.dot(self._g_up_p, up_meas), -1.0, 1.0))
        ang = float(np.arccos(dot))
        if ang > 0.6 and self._status in (
            CalibrationStatus.FULLY_ALIGNED,
            CalibrationStatus.YAW_UNCERTAIN,
            CalibrationStatus.ROLL_PITCH_VALID,
        ):
            # Could be hard acceleration; only flag if also far from |a|≈g and not a shock-only spike handled elsewhere.
            if abs(an - self.cfg.gravity_mps2) < 2.5:
                self._status = CalibrationStatus.REINITIALIZING
                self._clear_yaw()
                self._g_initialized = False
                self._g_up_p = None
                self._gravity_conf = 0.0

    def _clear_yaw(self) -> None:
        self._yaw = None
        self._yaw_axis = None
        self._scatter[:] = 0.0
        self._signed_sum[:] = 0.0
        self._axis_evidence = 0.0
        self._turn_evidence = 0.0
        self._gnss_sign_evidence = 0.0
        self._yaw_conf = 0.0
        self._last_yaw_update_t = None

    def _levelled_accel(self, acc_p: np.ndarray) -> np.ndarray:
        R_gp = rotation_gravity_up_to_vehicle_z(self._g_up_p)
        return R_gp @ acc_p

    def _gnss_quality_ok(self, t: float) -> bool:
        g = self._gnss
        if g is None:
            return False
        if (t - g.timestamp) > self.cfg.gnss_max_age_s:
            return False
        if g.hdop > self.cfg.gnss_max_hdop or g.num_sats < self.cfg.gnss_min_sats:
            return False
        if g.speed_mps < 0.0 or not np.isfinite(g.speed_mps) or not np.isfinite(g.hdop):
            return False
        return True

    def _accel_magnitudes_agree(self, a_h_n: float, gnss_abs: float) -> bool:
        hi = max(a_h_n, gnss_abs)
        lo = min(a_h_n, gnss_abs)
        if hi < 1e-9:
            return False
        return (hi <= lo * (1.0 + self.cfg.gnss_imu_agree_rel)) and ((hi - lo) <= self.cfg.gnss_imu_agree_abs)

    def _gnss_sign_ready(self, t: float, a_h_n: float) -> bool:
        if not self._gnss_quality_ok(t):
            return False
        if self._gnss.speed_mps < self.cfg.gnss_min_speed_mps:
            return False
        mag = abs(self._gnss_accel)
        if mag < self.cfg.gnss_min_accel or mag > self.cfg.gnss_max_abs_accel:
            return False
        return self._accel_magnitudes_agree(a_h_n, mag)

    def _update_yaw(self, t: float, acc_p: np.ndarray, gyro_p: np.ndarray, dt: float) -> None:
        R_gp = rotation_gravity_up_to_vehicle_z(self._g_up_p)
        acc_g = R_gp @ acc_p
        gyro_g = R_gp @ gyro_p
        a_h = acc_g[:2]
        a_h_n = float(np.linalg.norm(a_h))
        gyro_n = vector_norm(gyro_g)
        acc_n = vector_norm(acc_g)

        if acc_n > self.cfg.yaw_shock_accel_max:
            return

        straight = gyro_n < self.cfg.yaw_max_gyro_norm
        if straight and a_h_n >= self.cfg.yaw_min_horiz_accel:
            gnss_watch = self._gnss_quality_ok(t) and self._gnss.speed_mps >= self.cfg.gnss_min_speed_mps
            gnss_sign_ok = self._gnss_sign_ready(t, a_h_n)
            skip_non_long = gnss_watch and not gnss_sign_ok
            if not skip_non_long:
                outer = np.outer(a_h, a_h)
                self._scatter += outer * dt
                self._axis_evidence += a_h_n * dt
                if gnss_sign_ok:
                    sgn = 1.0 if self._gnss_accel >= 0.0 else -1.0
                    self._signed_sum += sgn * a_h * dt
                    self._gnss_sign_evidence += abs(self._gnss_accel) * dt
                self._last_yaw_update_t = t

        # Turn-based 180° disambiguation only after an axis exists.
        axis = self._principal_axis()
        if axis is not None and gyro_n >= self.cfg.yaw_turn_gyro_min and a_h_n >= 0.25:
            wz = float(gyro_g[2])
            n = np.array([-axis[1], axis[0]])
            lat = float(np.dot(a_h, n))
            # For +X forward, +Z up: a_y ≈ ω_z * v_x, v_x ≥ 0 ⇒ ω_z * a_y ≥ 0.
            self._turn_evidence += float(np.sign(wz)) * lat * dt
            self._last_yaw_update_t = t

        self._maybe_lock_yaw(t)

    def _principal_axis(self) -> np.ndarray | None:
        if self._axis_evidence < 0.25 * self.cfg.yaw_min_evidence:
            return None
        w, V = np.linalg.eigh(self._scatter)
        if w[1] <= 1e-12:
            return None
        ratio = w[1] / max(w[0], 1e-12)
        if ratio < self.cfg.yaw_pca_ratio_min:
            return None
        axis = V[:, 1]
        return axis

    def _maybe_lock_yaw(self, t: float) -> None:
        axis = self._principal_axis()
        if axis is None or self._axis_evidence < self.cfg.yaw_min_evidence:
            return
        self._yaw_axis = axis
        signed_n = float(np.linalg.norm(self._signed_sum))
        s_gnss = 0
        if self._gnss_sign_evidence >= self.cfg.gnss_sign_evidence_min and signed_n > 1e-6:
            dot = float(np.dot(self._signed_sum, axis))
            if abs(dot) > 1e-9:
                s_gnss = 1 if dot > 0.0 else -1
        s_turn = 0
        if abs(self._turn_evidence) >= self.cfg.yaw_turn_evidence_min:
            if abs(self._turn_evidence) > 1e-12:
                s_turn = 1 if self._turn_evidence > 0.0 else -1
        if s_gnss != 0 and s_turn != 0 and s_gnss != s_turn:
            self._yaw = None
            self._yaw_conf = min(self._yaw_conf, 0.25)
            return
        sign = float(s_gnss if s_gnss != 0 else s_turn)
        if sign == 0.0:
            self._yaw_conf = float(
                np.clip(self._axis_evidence / (self.cfg.yaw_min_evidence * 3.0), 0.0, 0.45)
            )
            return
        u = sign * axis
        yaw_new = -float(np.arctan2(u[1], u[0]))
        if self._yaw is not None:
            d = abs(math.atan2(math.sin(yaw_new - self._yaw), math.cos(yaw_new - self._yaw)))
            if d > self.cfg.yaw_disagree_rad:
                self._yaw = None
                self._yaw_conf = min(self._yaw_conf, 0.30)
                return
        self._yaw = yaw_new
        self._yaw_conf = float(
            np.clip(
                0.35 * min(1.0, self._axis_evidence / (self.cfg.yaw_min_evidence * 2.5))
                + 0.35 * min(1.0, abs(self._turn_evidence) / max(self.cfg.yaw_turn_evidence_min * 2.0, 1e-6))
                + 0.30 * min(1.0, self._gnss_sign_evidence / 1.5),
                0.0,
                1.0,
            )
        )
        if self._gnss_sign_evidence < self.cfg.gnss_sign_evidence_min:
            self._yaw_conf = min(self._yaw_conf, 0.85)
        self._last_yaw_update_t = t

    def _refresh_status(self, t: float) -> None:
        if self._status == CalibrationStatus.INVALID:
            return
        if not self._g_initialized:
            if self._status not in (
                CalibrationStatus.UNINITIALIZED,
                CalibrationStatus.STATIC_DETECTED,
                CalibrationStatus.REINITIALIZING,
            ):
                self._status = CalibrationStatus.UNINITIALIZED
            return

        yaw_stale = False
        if self._last_yaw_update_t is not None:
            yaw_stale = (t - self._last_yaw_update_t) > self.cfg.yaw_hold_s * 2.0
        if self._yaw is not None and yaw_stale:
            self._yaw = None
            self._yaw_conf = min(self._yaw_conf, 0.30)

        if self._yaw is not None and self._yaw_conf >= 0.35 and not yaw_stale:
            self._status = CalibrationStatus.FULLY_ALIGNED
            conf = self._compose_confidence()
            if conf.overall < self.cfg.fully_aligned_min_confidence:
                self._status = CalibrationStatus.YAW_UNCERTAIN
        elif self._yaw_axis is not None:
            self._status = CalibrationStatus.YAW_UNCERTAIN
        elif self._status == CalibrationStatus.REINITIALIZING:
            self._status = CalibrationStatus.ROLL_PITCH_VALID
        elif self._status != CalibrationStatus.DEGRADED:
            self._status = CalibrationStatus.ROLL_PITCH_VALID

    def _rebuild_rotation(self) -> None:
        if not self._g_initialized or self._g_up_p is None:
            self._R_vp = np.eye(3)
            self._q_pv = quat_identity()
            return
        R_gp = rotation_gravity_up_to_vehicle_z(self._g_up_p)
        if self._yaw is not None and self._status in (
            CalibrationStatus.FULLY_ALIGNED,
            CalibrationStatus.DEGRADED,
        ):
            self._R_vp = rotation_z(self._yaw) @ R_gp
        else:
            self._R_vp = R_gp
        self._q_pv = quatPhoneToVehicle(self._R_vp)

    def _compose_confidence(self) -> CalibrationConfidence:
        if self._last_gravity_update_t is not None and self._have_time:
            age = self._t_prev - self._last_gravity_update_t
            g_temp = float(np.clip(1.0 - age / 30.0, 0.0, 1.0))
        else:
            g_temp = 0.0
        if self._last_yaw_update_t is not None:
            y_temp = float(np.clip(1.0 - (self._t_prev - self._last_yaw_update_t) / self.cfg.yaw_hold_s, 0.0, 1.0))
        else:
            y_temp = 0.0
        temporal = 0.6 * g_temp + 0.4 * y_temp
        self._temporal_conf = temporal
        g = self._gravity_conf if self._g_initialized else 0.0
        y = self._yaw_conf if self._yaw is not None else (
            min(0.4, self._axis_evidence / max(self.cfg.yaw_min_evidence, 1e-6) * 0.2)
            if self._yaw_axis is not None
            else 0.0
        )
        s = self._sensor_quality
        if self._status == CalibrationStatus.FULLY_ALIGNED:
            overall = 0.30 * g + 0.45 * y + 0.15 * temporal + 0.10 * s
        elif self._status == CalibrationStatus.YAW_UNCERTAIN:
            overall = min(self.cfg.yaw_uncertain_confidence_cap, 0.70 * g + 0.10 * y + 0.10 * temporal + 0.10 * s)
        elif self._status in (CalibrationStatus.ROLL_PITCH_VALID, CalibrationStatus.DEGRADED):
            overall = min(0.50, 0.75 * g + 0.05 * y + 0.10 * temporal + 0.10 * s)
        elif self._status == CalibrationStatus.STATIC_DETECTED:
            overall = min(0.25, 0.5 * s)
        else:
            overall = min(0.15, 0.5 * s)
        if self._status in (CalibrationStatus.INVALID, CalibrationStatus.UNINITIALIZED):
            overall = 0.0 if self._status == CalibrationStatus.UNINITIALIZED else min(overall, 0.05)
        return CalibrationConfidence(
            overall=float(np.clip(overall, 0.0, 1.0)),
            gravity=float(np.clip(g, 0.0, 1.0)),
            yaw_observability=float(np.clip(y, 0.0, 1.0)),
            temporal=float(np.clip(temporal, 0.0, 1.0)),
            sensor_quality=float(np.clip(s, 0.0, 1.0)),
        )

    def _emit(
        self,
        t: float,
        acc_p: np.ndarray,
        gyro_p: np.ndarray,
        force_status: CalibrationStatus | None = None,
    ) -> AlignedIMUFrame:
        if is_finite_vec(acc_p) and is_finite_vec(gyro_p):
            acc_v = phoneToVehicleVector(self._R_vp, acc_p)
            gyro_v = phoneToVehicleVector(self._R_vp, gyro_p)
        else:
            acc_v = np.array(acc_p, dtype=float)
            gyro_v = np.array(gyro_p, dtype=float)
        status = force_status if force_status is not None else self._status
        conf = self._compose_confidence()
        if status == CalibrationStatus.INVALID:
            conf.overall = min(conf.overall, 0.05)
        frame = AlignedIMUFrame(
            timestamp=t,
            ax_v=float(acc_v[0]),
            ay_v=float(acc_v[1]),
            az_v=float(acc_v[2]),
            gx_v=float(gyro_v[0]),
            gy_v=float(gyro_v[1]),
            gz_v=float(gyro_v[2]),
            q_pv=self._q_pv.copy(),
            status=status,
            confidence=conf,
        )
        if status != CalibrationStatus.INVALID:
            self._last_good_frame = frame
        return frame
