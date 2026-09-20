from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CalibrationStatus(str, Enum):
    UNKNOWN = "unknown"
    STATIC_OK = "static_ok"
    YAW_PENDING = "yaw_pending"
    ALIGNED = "aligned"
    DEGRADED = "degraded"


class NavMode(str, Enum):
    INIT = "INIT"
    GNSS = "GNSS"
    GNSS_DEGRADED = "GNSS_DEGRADED"
    DEAD_RECKONING = "DEAD_RECKONING"


class GnssQuality(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OUTAGE = "OUTAGE"


class MapStatus(str, Enum):
    ON_NETWORK = "ON_NETWORK"
    OFF_NETWORK = "OFF_NETWORK"
    MAP_DATA_NOT_AVAILABLE = "MAP DATA NOT AVAILABLE"


@dataclass
class ImuSample:
    timestamp: float
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float


@dataclass
class AlignedImu:
    timestamp: float
    ax_v: float
    ay_v: float
    az_v: float
    gx_v: float
    gy_v: float
    gz_v: float
    q_pv: tuple[float, float, float, float]
    status: CalibrationStatus
    confidence: float


@dataclass
class GnssSample:
    timestamp: float
    lat: float
    lon: float
    alt: float
    speed: float
    hdop: float
    num_sats: int
    valid: bool


@dataclass
class SpeedEstimate:
    timestamp: float
    velocity_mps: float
    variance: float
    valid: bool
    reason: str = ""


@dataclass
class NavigationState:
    timestamp: float
    x: float
    y: float
    vx: float
    vy: float
    yaw: float
    bax: float
    bay: float
    bgz: float
    lat: float
    lon: float
    heading_deg: float
    speed_mps: float
    speed_valid: bool
    mode: NavMode
    pos_std_m: float
    P_diag: list[float] = field(default_factory=list)


@dataclass
class MapMatchedPosition:
    timestamp: float
    lat_snapped: float
    lon_snapped: float
    heading_snapped_deg: float
    road_segment_id: int
    confidence_score: float
    is_on_road_network: bool
    status: MapStatus


@dataclass
class IdrOutput:
    timestamp: float
    lat: float
    lon: float
    heading_deg: float
    speed_mps: float
    speed_kmh: float | None
    speed_valid: bool
    speed_display: str
    mode: NavMode
    gnss_quality: GnssQuality
    map_status: MapStatus
    map_confidence: float
    road_segment_id: int
    alignment_status: CalibrationStatus
    alignment_confidence: float
    v2x_decision: str
    pos_std_m: float
    sats: int
    hdop: float
    gnss_age_s: float
    gt_lat: float
    gt_lon: float
    naive_lat: float
    naive_lon: float
    ekf_lat: float
    ekf_lon: float
    matched_lat: float
    matched_lon: float
    error_idr_m: float
    error_naive_m: float
    error_gnss_m: float | None
    tunnel: bool
    simulated_outage: bool
