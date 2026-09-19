from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

EARTH_RADIUS_M = 6378137.0
CHI2_DOF2_P95 = 5.991
CHI2_DOF2_P99 = 9.210
MAX_PASSENGER_SPEED_MPS = 55.0


class MessageType(IntEnum):
    UNKNOWN = 0
    CAM_LIKE = 1
    BSM_LIKE = 2
    RELATIVE = 3
    REPLAY = 4
    TEST_FIXTURE = 5


class MessageSource(IntEnum):
    UNKNOWN = 0
    SIMULATOR = 1
    REPLAY = 2
    UDP = 3
    TEST_FIXTURE = 4
    HARDWARE_OBU = 5  # reserved; MODE A has no OBU


class SourceQuality(IntEnum):
    UNKNOWN = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class SecurityStatus(IntEnum):
    RECEIVED = 0
    UNVERIFIED = 1
    UNTRUSTED = 2
    INVALID = 3
    REJECTED = 4
    STALE = 5
    VALIDATED = 6
    AUTHENTICATED = 7


class GateDecision(IntEnum):
    REJECT = 0
    DOWNWEIGHT = 1
    ACCEPT = 2
    UNAVAILABLE = 3


class CooperativeKind(IntEnum):
    NONE = 0
    RELATIVE_TRANSFER_POSITION = 1
    EXPLICIT_RELATIVE = 2
    CLUSTER_CONSENSUS = 3


@dataclass
class EnuOrigin:
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    altitude_m: float = 0.0
    valid: bool = False


@dataclass
class GeoPosition:
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    altitude_m: float = 0.0


@dataclass
class EnuVector:
    east_m: float = 0.0
    north_m: float = 0.0
    up_m: float = 0.0


@dataclass
class TimestampPair:
    sender_time_s: float = 0.0
    receive_time_s: float = 0.0
    clock_offset_s: float = 0.0
    jitter_s: float = 0.0


@dataclass
class NormalizedV2XMessage:
    vehicle_id: str = ""
    time: TimestampPair = field(default_factory=TimestampPair)
    geo: GeoPosition = field(default_factory=GeoPosition)
    velocity_enu: EnuVector = field(default_factory=EnuVector)
    acceleration_enu: EnuVector = field(default_factory=EnuVector)
    heading_rad: float = 0.0
    yaw_rate_rps: float = 0.0
    length_m: float = 0.0
    width_m: float = 0.0
    message_type: MessageType = MessageType.CAM_LIKE
    source: MessageSource = MessageSource.SIMULATOR
    quality: SourceQuality = SourceQuality.MEDIUM
    declared_security: SecurityStatus = SecurityStatus.UNVERIFIED
    declared_pos_std_m: float = 5.0
    declared_vel_std_mps: float = 1.0
    has_explicit_relative: bool = False
    relative_enu: EnuVector = field(default_factory=EnuVector)
    relative_std_m: float = 0.0


@dataclass
class LocalNavigationState:
    timestamp_s: float = 0.0
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    altitude_m: float = 0.0
    v_x: float = 0.0
    v_y: float = 0.0
    yaw_rad: float = 0.0
    position_cov_ne: list = field(default_factory=lambda: [[25.0, 0.0], [0.0, 25.0]])
    gnss_available: bool = False
    valid: bool = False


@dataclass
class V2XConfig:
    origin_latitude_deg: float = 12.9716
    origin_longitude_deg: float = 77.5946
    origin_altitude_m: float = 920.0
    origin_locked: bool = False
    max_speed_mps: float = MAX_PASSENGER_SPEED_MPS
    max_accel_mps2: float = 12.0
    max_yaw_rate_rps: float = 1.5
    max_message_age_s: float = 1.5
    downweight_age_s: float = 0.40
    min_dt_s: float = 1.0e-4
    track_timeout_s: float = 3.0
    reject_jump_m: float = 80.0
    max_rel_process_std_mps: float = 4.0
    relative_snapshot_max_age_s: float = 30.0
    age_time_constant_s: float = 0.20
    clock_offset_std_s: float = 0.020
    nis_accept: float = CHI2_DOF2_P95
    nis_reject: float = CHI2_DOF2_P99
    downweight_scale: float = 4.0
    reject_untrusted: bool = True
    reject_unverified: bool = False
    allow_claimed_authenticated_simulation: bool = False
    min_pos_std_m: float = 1.0
    max_pos_std_m: float = 50.0
    quality_low_scale: float = 2.5
    quality_medium_scale: float = 1.0
    quality_high_scale: float = 0.7
    max_vehicles: int = 32
