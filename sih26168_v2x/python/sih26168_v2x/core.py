from __future__ import annotations

from dataclasses import dataclass

from .cooperative import (
    CooperativeMeasurement,
    RemoteState,
    RemoteTrack,
    fuse_tracks,
    should_use_measurement,
    update_relative_snapshot,
)
from .frames import geo_to_local_enu, wrap_pi
from .security import MockSecurityProvider
from .types import (
    EnuOrigin,
    GateDecision,
    LocalNavigationState,
    NormalizedV2XMessage,
    SecurityStatus,
    V2XConfig,
)
from .validation import validate_kinematics


@dataclass
class HealthStatus:
    received: int = 0
    validated: int = 0
    rejected: int = 0
    stale: int = 0
    duplicates: int = 0
    out_of_order: int = 0


@dataclass
class CooperativeMeasurementResult:
    decision: GateDecision = GateDecision.UNAVAILABLE
    measurement: CooperativeMeasurement | None = None
    nis: float = 0.0
    reason: str = "no_v2x"


class V2XCore:
    def __init__(self, config: V2XConfig | None = None):
        self.cfg = config or V2XConfig()
        self.origin = EnuOrigin(
            self.cfg.origin_latitude_deg,
            self.cfg.origin_longitude_deg,
            self.cfg.origin_altitude_m,
            self.cfg.origin_locked,
        )
        self.security = MockSecurityProvider()
        self.tracks: dict[str, RemoteTrack] = {}
        self.health = HealthStatus()

    def reset(self) -> None:
        self.tracks.clear()
        self.health = HealthStatus()
        if not self.cfg.origin_locked:
            self.origin.valid = False

    def lock_origin(self, origin: EnuOrigin) -> None:
        self.origin = origin
        self.origin.valid = True
        self.cfg.origin_locked = True

    def ingest(self, message: NormalizedV2XMessage) -> None:
        self.health.received += 1
        sec, _reason = self.security.evaluate(message, self.cfg)
        if sec in (SecurityStatus.REJECTED, SecurityStatus.INVALID):
            self.health.rejected += 1
            return
        tr = self.tracks.get(message.vehicle_id)
        last_t = tr.last_sender_time_s if tr else -1.0
        last_geo = tr.last_geo if tr else None
        kin = validate_kinematics(message, self.cfg, last_t, last_geo)
        if kin.duplicate:
            self.health.duplicates += 1
            self.health.rejected += 1
            return
        if kin.out_of_order:
            self.health.out_of_order += 1
            self.health.rejected += 1
            return
        if kin.disposition == SecurityStatus.STALE:
            self.health.stale += 1
            self.health.rejected += 1
            return
        if kin.disposition != SecurityStatus.VALIDATED:
            self.health.rejected += 1
            return
        if len(self.tracks) >= self.cfg.max_vehicles and message.vehicle_id not in self.tracks:
            self.health.rejected += 1
            return
        if not self.origin.valid:
            self.origin = EnuOrigin(
                self.cfg.origin_latitude_deg,
                self.cfg.origin_longitude_deg,
                self.cfg.origin_altitude_m,
                True,
            )
        if tr is None:
            tr = RemoteTrack()
            self.tracks[message.vehicle_id] = tr
        st = RemoteState(
            vehicle_id=message.vehicle_id,
            timestamp_s=message.time.sender_time_s,
            geo=message.geo,
            position_enu=geo_to_local_enu(message.geo, self.origin),
            velocity_enu=message.velocity_enu,
            quality=message.quality,
            age_s=kin.age_s,
            pos_std_m=message.declared_pos_std_m,
            usable=True,
            has_explicit_relative=message.has_explicit_relative,
            relative_enu=message.relative_enu,
            relative_std_m=message.relative_std_m,
        )
        tr.state = st
        tr.last_sender_time_s = message.time.sender_time_s
        tr.last_geo = message.geo
        tr.updates += 1
        self.health.validated += 1
        _ = wrap_pi(message.heading_rad)

    def get_cooperative_measurement(self, local: LocalNavigationState) -> CooperativeMeasurementResult:
        if local.valid and not self.origin.valid:
            self.origin = EnuOrigin(local.latitude_deg, local.longitude_deg, local.altitude_m, True)
        now = local.timestamp_s
        self.tracks = {
            k: v for k, v in self.tracks.items() if now - v.state.timestamp_s <= self.cfg.track_timeout_s
        }
        if local.valid and local.gnss_available:
            for tr in self.tracks.values():
                update_relative_snapshot(tr, local, self.origin)
        result = CooperativeMeasurementResult()
        if not self.tracks or not local.valid:
            result.reason = "no_v2x" if not self.tracks else "invalid_local"
            return result
        meas = fuse_tracks(list(self.tracks.values()), local, self.origin, self.cfg)
        result.measurement = meas
        if not meas.has_position:
            result.reason = "correlated_with_gnss" if local.gnss_available else "no_observable_relative"
            return result
        if self.cfg.downweight_age_s < meas.age_s <= self.cfg.max_message_age_s:
            meas.position_cov_ne[0][0] *= self.cfg.downweight_scale
            meas.position_cov_ne[1][1] *= self.cfg.downweight_scale
        decision, nis, reason = should_use_measurement(local, self.origin, meas, self.cfg)
        result.decision = decision
        result.nis = nis
        result.reason = reason
        if decision == GateDecision.DOWNWEIGHT:
            meas.position_cov_ne[0][0] *= self.cfg.downweight_scale
            meas.position_cov_ne[1][1] *= self.cfg.downweight_scale
        if decision == GateDecision.REJECT:
            meas.has_position = False
        return result
