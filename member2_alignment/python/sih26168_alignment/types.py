"""Public types, configuration, and calibration state for Member 2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import numpy as np


class CalibrationStatus(IntEnum):
    """Calibration state machine. Integer values are shared with C++."""

    UNINITIALIZED = 0
    STATIC_DETECTED = 1
    ROLL_PITCH_VALID = 2
    YAW_UNCERTAIN = 3
    FULLY_ALIGNED = 4
    DEGRADED = 5
    REINITIALIZING = 6
    INVALID = 7


@dataclass
class FrameAlignerConfig:
    gravity_mps2: float = 9.80665
    sample_rate_hz: float = 100.0

    static_window_samples: int = 50
    static_accel_var_max: float = 0.08
    static_gyro_norm_max: float = 0.04
    static_accel_norm_tol: float = 0.18
    static_dir_align_rad: float = 0.10
    min_static_duration_s: float = 0.40

    gravity_ema_alpha: float = 0.08
    gravity_max_tilt_jump_rad: float = 0.25

    yaw_min_horiz_accel: float = 0.45
    yaw_max_gyro_norm: float = 0.18
    yaw_shock_accel_max: float = 16.0
    yaw_min_evidence: float = 1.6
    yaw_pca_ratio_min: float = 2.2
    yaw_turn_gyro_min: float = 0.20
    yaw_turn_evidence_min: float = 0.8
    yaw_hold_s: float = 8.0

    gnss_max_hdop: float = 2.5
    gnss_min_sats: int = 6
    gnss_max_age_s: float = 0.50
    gnss_min_accel: float = 0.35
    gnss_min_speed_mps: float = 2.0
    gnss_max_abs_accel: float = 6.0
    gnss_imu_agree_rel: float = 0.16
    gnss_imu_agree_abs: float = 0.35
    gnss_sign_evidence_min: float = 0.80
    yaw_disagree_rad: float = 0.60

    max_accel_norm: float = 80.0
    max_gyro_norm: float = 25.0
    max_dt_s: float = 0.050
    min_dt_s: float = 1.0e-4
    gap_reset_s: float = 1.0

    fully_aligned_min_confidence: float = 0.62
    yaw_uncertain_confidence_cap: float = 0.55

    def nominal_dt(self) -> float:
        return 1.0 / self.sample_rate_hz


@dataclass
class CalibrationConfidence:
    """Each term is in [0, 1] with documented physical meaning.

    gravity: inverse of recent gravity-direction variance during static/levelled operation.
    yaw_observability: how strongly a unique longitudinal axis (+sign) has been observed.
    temporal: how recently supporting evidence was refreshed.
    sensor_quality: fraction of recent samples that passed validation.
    overall: weighted combination; never claimed to be a probability.
    """

    overall: float = 0.0
    gravity: float = 0.0
    yaw_observability: float = 0.0
    temporal: float = 0.0
    sensor_quality: float = 1.0


@dataclass
class AlignedIMUFrame:
    timestamp: float
    ax_v: float
    ay_v: float
    az_v: float
    gx_v: float
    gy_v: float
    gz_v: float
    q_pv: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    status: CalibrationStatus = CalibrationStatus.UNINITIALIZED
    confidence: CalibrationConfidence = field(default_factory=CalibrationConfidence)

    def accel_v(self) -> np.ndarray:
        return np.array([self.ax_v, self.ay_v, self.az_v], dtype=float)

    def gyro_v(self) -> np.ndarray:
        return np.array([self.gx_v, self.gy_v, self.gz_v], dtype=float)


@dataclass
class OptionalGnssAid:
    timestamp: float
    speed_mps: float
    hdop: float = 99.0
    num_sats: int = 0
    course_rad: Optional[float] = None
    course_valid: bool = False
