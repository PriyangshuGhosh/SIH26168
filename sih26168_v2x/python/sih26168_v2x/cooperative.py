from __future__ import annotations

import math
from dataclasses import dataclass, field

from .frames import geo_to_local_enu, vehicle_frame_to_navigation_enu
from .timestamp import age_inflation_scale, time_sync_position_std_m
from .types import (
    CooperativeKind,
    EnuOrigin,
    EnuVector,
    GateDecision,
    GeoPosition,
    LocalNavigationState,
    SourceQuality,
    V2XConfig,
)
from .validation import speed_magnitude


@dataclass
class RelativeSnapshot:
    time_s: float = 0.0
    r_enu: EnuVector = field(default_factory=EnuVector)
    cov_m2: float = 25.0
    valid: bool = False


@dataclass
class RemoteState:
    vehicle_id: str = ""
    timestamp_s: float = 0.0
    geo: GeoPosition = field(default_factory=GeoPosition)
    position_enu: EnuVector = field(default_factory=EnuVector)
    velocity_enu: EnuVector = field(default_factory=EnuVector)
    quality: SourceQuality = SourceQuality.MEDIUM
    age_s: float = 0.0
    pos_std_m: float = 5.0
    usable: bool = False
    has_explicit_relative: bool = False
    relative_enu: EnuVector = field(default_factory=EnuVector)
    relative_std_m: float = 0.0


@dataclass
class RemoteTrack:
    state: RemoteState = field(default_factory=RemoteState)
    last_sender_time_s: float = -1.0
    last_geo: GeoPosition | None = None
    relative: RelativeSnapshot = field(default_factory=RelativeSnapshot)
    updates: int = 0


@dataclass
class CooperativeMeasurement:
    timestamp_s: float = 0.0
    north_m: float = 0.0
    east_m: float = 0.0
    position_cov_ne: list = field(default_factory=lambda: [[1e6, 0.0], [0.0, 1e6]])
    kind: CooperativeKind = CooperativeKind.NONE
    age_s: float = 0.0
    contributing_vehicles: int = 0
    has_position: bool = False


def _invert2(a):
    det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    if not math.isfinite(det) or abs(det) < 1e-18:
        return None
    return [[a[1][1] / det, -a[0][1] / det], [-a[1][0] / det, a[0][0] / det]]


def mahalanobis2(dn: float, de: float, s_ne) -> float:
    inv = _invert2(s_ne)
    if inv is None:
        return 1.0e9
    return dn * (inv[0][0] * dn + inv[0][1] * de) + de * (inv[1][0] * dn + inv[1][1] * de)


def should_use_measurement(local: LocalNavigationState, origin: EnuOrigin, meas: CooperativeMeasurement,
                           cfg: V2XConfig):
    if not meas.has_position or not local.valid or not origin.valid:
        return GateDecision.UNAVAILABLE, 0.0, "unavailable"
    p = geo_to_local_enu(GeoPosition(local.latitude_deg, local.longitude_deg, local.altitude_m), origin)
    dn = meas.north_m - p.north_m
    de = meas.east_m - p.east_m
    s = [
        [local.position_cov_ne[0][0] + meas.position_cov_ne[0][0],
         local.position_cov_ne[0][1] + meas.position_cov_ne[0][1]],
        [local.position_cov_ne[1][0] + meas.position_cov_ne[1][0],
         local.position_cov_ne[1][1] + meas.position_cov_ne[1][1]],
    ]
    nis = mahalanobis2(dn, de, s)
    if not math.isfinite(nis):
        return GateDecision.REJECT, nis, "non_finite_nis"
    if nis > cfg.nis_reject:
        return GateDecision.REJECT, nis, "nis_reject"
    if nis > cfg.nis_accept:
        return GateDecision.DOWNWEIGHT, nis, "nis_downweight"
    return GateDecision.ACCEPT, nis, "nis_accept"


def update_relative_snapshot(track: RemoteTrack, local: LocalNavigationState, origin: EnuOrigin) -> None:
    if not local.valid or not local.gnss_available or not origin.valid or not track.state.usable:
        return
    p_ego = geo_to_local_enu(GeoPosition(local.latitude_deg, local.longitude_deg, local.altitude_m), origin)
    p_rem = track.state.position_enu
    track.relative.time_s = local.timestamp_s
    track.relative.r_enu = EnuVector(p_rem.east_m - p_ego.east_m, p_rem.north_m - p_ego.north_m, 0.0)
    pnn = local.position_cov_ne[0][0]
    pee = local.position_cov_ne[1][1]
    track.relative.cov_m2 = max(1.0, 0.5 * (pnn + pee) + track.state.pos_std_m ** 2)
    track.relative.valid = True


def fuse_tracks(tracks: list[RemoteTrack], local: LocalNavigationState, origin: EnuOrigin,
                cfg: V2XConfig) -> CooperativeMeasurement:
    meas = CooperativeMeasurement(timestamp_s=local.timestamp_s)
    if not local.valid or not origin.valid or local.gnss_available:
        return meas
    ve_ego, vn_ego = vehicle_frame_to_navigation_enu(local.v_x, local.v_y, local.yaw_rad)
    cands = []
    for tr in tracks:
        if not tr.state.usable:
            continue
        age_s = age_inflation_scale(tr.state.age_s, cfg.age_time_constant_s)
        spd = speed_magnitude(tr.state.velocity_enu)
        tsync = time_sync_position_std_m(cfg.clock_offset_std_s, spd)
        qs = {SourceQuality.LOW: cfg.quality_low_scale, SourceQuality.HIGH: cfg.quality_high_scale}.get(
            tr.state.quality, cfg.quality_medium_scale)
        std_m = min(cfg.max_pos_std_m, max(cfg.min_pos_std_m, tr.state.pos_std_m * qs * age_s))
        if tr.state.has_explicit_relative:
            e = tr.state.position_enu.east_m - tr.state.relative_enu.east_m
            n = tr.state.position_enu.north_m - tr.state.relative_enu.north_m
            rstd = tr.state.relative_std_m if tr.state.relative_std_m > 0 else std_m
            var = std_m ** 2 + rstd ** 2 + tsync ** 2
            cands.append((n, e, var, tr.state.age_s, CooperativeKind.EXPLICIT_RELATIVE))
            continue
        if tr.relative.valid and (local.timestamp_s - tr.relative.time_s) <= cfg.relative_snapshot_max_age_s:
            dt = max(0.0, local.timestamp_s - tr.relative.time_s)
            r_e = tr.relative.r_enu.east_m + (tr.state.velocity_enu.east_m - ve_ego) * dt
            r_n = tr.relative.r_enu.north_m + (tr.state.velocity_enu.north_m - vn_ego) * dt
            proc = cfg.max_rel_process_std_mps * dt
            var = std_m ** 2 + tr.relative.cov_m2 + proc ** 2 + tsync ** 2
            e = tr.state.position_enu.east_m - r_e
            n = tr.state.position_enu.north_m - r_n
            cands.append((n, e, var, tr.state.age_s, CooperativeKind.RELATIVE_TRANSFER_POSITION))
    if not cands:
        return meas
    if len(cands) >= 3:
        ns = sorted(c[0] for c in cands)
        med = ns[len(ns) // 2]
        cands = [c for c in cands if abs(c[0] - med) < 40.0] or cands
    wsum = n = e = age = 0.0
    for cn, ce, var, ag, _k in cands:
        w = 1.0 / max(var, 1e-6)
        wsum += w
        n += w * cn
        e += w * ce
        age += w * ag
    meas.north_m = n / wsum
    meas.east_m = e / wsum
    meas.age_s = age / wsum
    fused = 1.0 / wsum
    meas.position_cov_ne = [[fused, 0.0], [0.0, fused]]
    meas.has_position = True
    meas.contributing_vehicles = len(cands)
    meas.kind = CooperativeKind.CLUSTER_CONSENSUS if len(cands) > 1 else cands[0][4]
    return meas
