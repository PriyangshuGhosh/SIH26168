from __future__ import annotations

import math
from dataclasses import dataclass

from .frames import finite_number, geo_to_local_enu, valid_latitude, valid_longitude
from .timestamp import evaluate_timing
from .types import EnuOrigin, EnuVector, GeoPosition, NormalizedV2XMessage, SecurityStatus, V2XConfig


def speed_magnitude(v: EnuVector) -> float:
    return math.sqrt(v.east_m ** 2 + v.north_m ** 2 + v.up_m ** 2)


def accel_magnitude(a: EnuVector) -> float:
    return math.sqrt(a.east_m ** 2 + a.north_m ** 2 + a.up_m ** 2)


def is_finite_message(msg: NormalizedV2XMessage) -> bool:
    vals = [
        msg.time.sender_time_s, msg.time.receive_time_s, msg.time.clock_offset_s,
        msg.geo.latitude_deg, msg.geo.longitude_deg, msg.geo.altitude_m,
        msg.velocity_enu.east_m, msg.velocity_enu.north_m, msg.velocity_enu.up_m,
        msg.acceleration_enu.east_m, msg.acceleration_enu.north_m, msg.acceleration_enu.up_m,
        msg.heading_rad, msg.yaw_rate_rps, msg.declared_pos_std_m, msg.declared_vel_std_mps,
    ]
    return all(finite_number(v) for v in vals)


@dataclass
class ValidationResult:
    disposition: SecurityStatus = SecurityStatus.INVALID
    reason: str = ""
    age_s: float = 0.0
    duplicate: bool = False
    out_of_order: bool = False


def validate_kinematics(msg: NormalizedV2XMessage, cfg: V2XConfig, last_sender_time_s: float,
                        last_geo: GeoPosition | None) -> ValidationResult:
    r = ValidationResult()
    if not msg.vehicle_id:
        r.reason = "empty_id"
        return r
    if not is_finite_message(msg):
        r.reason = "non_finite"
        return r
    if not valid_latitude(msg.geo.latitude_deg) or not valid_longitude(msg.geo.longitude_deg):
        r.reason = "invalid_coordinates"
        return r
    if msg.declared_pos_std_m <= 0.0 or msg.declared_vel_std_mps < 0.0:
        r.reason = "invalid_covariance"
        return r
    if speed_magnitude(msg.velocity_enu) > cfg.max_speed_mps:
        r.reason = "impossible_speed"
        return r
    if accel_magnitude(msg.acceleration_enu) > cfg.max_accel_mps2:
        r.reason = "impossible_accel"
        return r
    if abs(msg.yaw_rate_rps) > cfg.max_yaw_rate_rps:
        r.reason = "impossible_yaw_rate"
        return r
    timing = evaluate_timing(msg.time, last_sender_time_s, cfg.max_message_age_s, cfg.min_dt_s)
    r.age_s = timing.message_age_s
    r.duplicate = timing.duplicate
    r.out_of_order = timing.out_of_order
    if timing.stale:
        r.disposition = SecurityStatus.STALE
        r.reason = "stale_or_future"
        return r
    if timing.duplicate:
        r.reason = "duplicate"
        return r
    if timing.out_of_order:
        r.reason = "out_of_order"
        return r
    if last_geo is not None:
        tmp = EnuOrigin(last_geo.latitude_deg, last_geo.longitude_deg, last_geo.altitude_m, True)
        jump = geo_to_local_enu(msg.geo, tmp)
        jm = math.sqrt(jump.east_m ** 2 + jump.north_m ** 2)
        if jm > cfg.reject_jump_m:
            r.reason = "impossible_jump"
            return r
    r.disposition = SecurityStatus.VALIDATED
    r.reason = "ok"
    return r
