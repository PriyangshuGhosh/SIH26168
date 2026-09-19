"""Headless demo engine: simulator → V2XCore → toy filters. No UI fusion math."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from sih26168_v2x.cooperative import fuse_tracks, should_use_measurement
from sih26168_v2x.core import V2XCore
from sih26168_v2x.experiments import ToyEKF
from sih26168_v2x.frames import geo_to_local_enu, local_enu_to_geo
from sih26168_v2x.simulator import RemoteTruth, SimConfig, V2XSimulator, truth_at
from sih26168_v2x.types import (
    EnuOrigin,
    EnuVector,
    GateDecision,
    LocalNavigationState,
    NormalizedV2XMessage,
    V2XConfig,
)

from .scenarios import DemoSpec, SCENARIO_PRESETS, caption_at, recording_spec

EGO_SPEED_MPS = 16.0
ORIGIN = EnuOrigin(12.9716, 77.5946, 920.0, True)


@dataclass
class VehicleView:
    vehicle_id: str
    east_m: float
    north_m: float
    heading_rad: float
    is_ego: bool = False
    is_bad: bool = False
    ingest_ok: bool = False
    gate: str = "none"
    nis: float = 0.0
    age_s: float = 0.0
    pos_std_m: float = 0.0
    stale: bool = False


@dataclass
class LinkEvent:
    vehicle_id: str
    gate: str
    nis: float
    age_s: float
    pos_std_m: float
    ttl: float = 0.9


@dataclass
class DemoFrame:
    t: float
    gnss_available: bool
    caption: str
    ego_truth_e: float
    ego_truth_n: float
    ego_heading: float
    baseline_e: float
    baseline_n: float
    v2x_e: float
    v2x_n: float
    baseline_err_m: float
    v2x_err_m: float
    vehicles: list[VehicleView]
    links: list[LinkEvent]
    accepted: int
    downweighted: int
    rejected: int
    ingest_rejected: int
    validated: int
    received: int
    n_remotes: int
    messages_this_step: int
    fused_age_s: float
    fused_nis: float
    fused_decision: str
    fused_reason: str
    fused_contributors: int
    error_history: list[tuple[float, float, float]]
    paused: bool
    demo_mode: bool
    story_index: int
    gnss_banner: bool = False
    bad_banner: bool = False
    show_endcard: bool = False
    v2x_status: str = "NONE"
    meas_status: str = "COOPERATIVE MEASUREMENT UNAVAILABLE"
    reject_nis: float = 0.0
    reject_vehicle_id: str = ""


@dataclass
class DemoEngine:
    spec: DemoSpec = field(default_factory=recording_spec)
    paused: bool = True

    def __post_init__(self) -> None:
        self.reset(self.spec)

    def reset(self, spec: DemoSpec | None = None) -> None:
        if spec is not None:
            self.spec = spec
        self.t = 0.0
        self.paused = not self.spec.demo_mode
        self.manual_outage = False
        self.pending_bad = False
        self.bad_injected = False
        self._bad_id: str | None = None
        self.gnss_lost_at: float | None = None
        self.bad_event_at: float | None = None
        self._prev_gnss = True
        self.accepted = 0
        self.downweighted = 0
        self.rejected_gate = 0
        self.messages_this_step = 0
        self.fused_age_s = 0.0
        self.fused_nis = 0.0
        self.fused_decision = GateDecision.UNAVAILABLE.name
        self.fused_reason = "no_v2x"
        self.fused_contributors = 0
        self.links: list[LinkEvent] = []
        self.error_history: list[tuple[float, float, float]] = []
        self.truth_path: list[tuple[float, float]] = []
        self.baseline_path: list[tuple[float, float]] = []
        self.v2x_path: list[tuple[float, float]] = []
        self._last_ingest_ok: dict[str, bool] = {}
        self.imu_rng = random.Random(self.spec.seed + 1000)
        remotes = [
            RemoteTruth(
                f"R{i + 1}",
                0.0,
                EGO_SPEED_MPS + (i % 3) * 0.4,
                0.0,
                18.0 + 8.0 * i,
                3.7 * ((i % 3) - 1),
                pos_std_m=self.spec.pos_std_m,
            )
            for i in range(self.spec.n_remotes)
        ]
        sim_cfg = SimConfig(
            seed=self.spec.seed,
            origin_lat=ORIGIN.latitude_deg,
            origin_lon=ORIGIN.longitude_deg,
            origin_alt=ORIGIN.altitude_m,
            dt_s=self.spec.dt_s,
            packet_loss=self.spec.packet_loss,
            latency_mean_s=self.spec.latency_mean_s,
            latency_jitter_s=self.spec.latency_jitter_s,
            out_of_order_rate=self.spec.out_of_order_rate,
            remotes=remotes,
        )
        self.sim = V2XSimulator(sim_cfg)
        self.core = V2XCore(
            V2XConfig(origin_locked=True, max_vehicles=32, reject_jump_m=500.0)
        )
        self.core.lock_origin(ORIGIN)
        self.baseline = ToyEKF()
        self.v2x_ekf = ToyEKF()
        self._step_count = 0

    def set_remote_count(self, n: int) -> None:
        spec = replace(self.spec, n_remotes=max(0, int(n)), name=f"n{n}")
        self.reset(spec)

    def trigger_gnss_outage(self) -> None:
        self.manual_outage = True

    def restore_gnss(self) -> None:
        self.manual_outage = False

    def inject_bad_vehicle(self) -> None:
        self.pending_bad = True

    def start_demo_mode(self) -> None:
        self.reset(recording_spec())
        self.paused = False

    def gnss_available(self, t: float | None = None) -> bool:
        tt = self.t if t is None else t
        if self.manual_outage:
            return False
        start = self.spec.gnss_outage_s
        if start is None:
            return True
        if tt + 1e-12 < start:
            return True
        restore = self.spec.gnss_restore_s
        if restore is None:
            return False
        return tt + 1e-12 >= restore

    def _maybe_scripted_events(self) -> None:
        spec = self.spec
        if spec.inject_bad_at_s is not None and not self.bad_injected:
            if self.t + 1e-12 >= spec.inject_bad_at_s:
                self.pending_bad = True

    def _apply_bad(self, msgs: list[NormalizedV2XMessage]) -> list[NormalizedV2XMessage]:
        if self.pending_bad and msgs:
            self._bad_id = msgs[0].vehicle_id
            self.pending_bad = False
            self.bad_injected = True
            if self.bad_event_at is None:
                self.bad_event_at = self.t
        if not self.bad_injected or not self._bad_id:
            return msgs
        for m in msgs:
            if m.vehicle_id != self._bad_id:
                continue
            enu = geo_to_local_enu(m.geo, ORIGIN)
            enu.east_m += self.spec.bad_offset_east_m
            m.geo = local_enu_to_geo(enu, ORIGIN)
            m.declared_pos_std_m = max(m.declared_pos_std_m, 3.0)
        return msgs

    def _local_from_ekf(self, ekf: ToyEKF, gnss: bool) -> LocalNavigationState:
        geo = local_enu_to_geo(EnuVector(ekf.e, ekf.n, 0.0), ORIGIN)
        return LocalNavigationState(
            timestamp_s=self.t,
            latitude_deg=geo.latitude_deg,
            longitude_deg=geo.longitude_deg,
            altitude_m=ORIGIN.altitude_m,
            v_x=math.hypot(ekf.vn, ekf.ve),
            v_y=0.0,
            yaw_rad=0.0,
            position_cov_ne=[[ekf.pn, 0.0], [0.0, ekf.pe]],
            gnss_available=gnss,
            valid=True,
        )

    def step(self) -> DemoFrame:
        if self.paused:
            return self.snapshot()
        dt = self.spec.dt_s
        self._maybe_scripted_events()
        gnss = self.gnss_available()
        if self._prev_gnss and not gnss:
            self.gnss_lost_at = self.t
        elif gnss:
            self.gnss_lost_at = None
        self._prev_gnss = gnss
        n_true = EGO_SPEED_MPS * self.t
        e_true = 0.0
        imu_an = self.imu_rng.gauss(0.0, 0.35)
        imu_ae = self.imu_rng.gauss(0.0, 0.35)
        gnss_n = n_true + self.imu_rng.gauss(0.0, 1.5)
        gnss_e = e_true + self.imu_rng.gauss(0.0, 1.5)
        ai_speed = EGO_SPEED_MPS + self.imu_rng.gauss(0.0, 0.3)

        for ekf in (self.baseline, self.v2x_ekf):
            ekf.predict(dt, imu_an, imu_ae)
            ekf.update_speed(ai_speed, 0.2)
            if gnss:
                ekf.update_gnss(gnss_n, gnss_e, 4.0)

        msgs = self.sim.messages_at(self.t)
        msgs = self._apply_bad(msgs)
        self.messages_this_step = len(msgs)
        self._last_ingest_ok = {}
        before = {vid: tr.updates for vid, tr in self.core.tracks.items()}
        recv0 = self.core.health.received
        for m in msgs:
            self.core.ingest(m)
            after_upd = self.core.tracks.get(m.vehicle_id)
            ok = after_upd is not None and after_upd.updates > before.get(m.vehicle_id, 0)
            self._last_ingest_ok[m.vehicle_id] = ok
        assert self.core.health.received == recv0 + len(msgs)

        local = self._local_from_ekf(self.v2x_ekf, gnss)
        result = self.core.get_cooperative_measurement(local)
        self.fused_decision = result.decision.name
        self.fused_reason = result.reason
        self.fused_nis = result.nis
        self.fused_age_s = result.measurement.age_s if result.measurement else 0.0
        self.fused_contributors = (
            result.measurement.contributing_vehicles if result.measurement else 0
        )
        if result.decision == GateDecision.ACCEPT:
            self.accepted += 1
        elif result.decision == GateDecision.DOWNWEIGHT:
            self.downweighted += 1
        elif result.decision == GateDecision.REJECT:
            self.rejected_gate += 1

        if (
            result.measurement
            and result.measurement.has_position
            and result.decision in (GateDecision.ACCEPT, GateDecision.DOWNWEIGHT)
        ):
            var = result.measurement.position_cov_ne[0][0]
            self.v2x_ekf.update_v2x(
                result.measurement.north_m,
                result.measurement.east_m,
                var,
                True,
                result.nis,
            )

        for lk in self.links:
            lk.ttl -= dt
        self.links = [lk for lk in self.links if lk.ttl > 0.0]
        by_id = {lk.vehicle_id: i for i, lk in enumerate(self.links)}
        for vid, ingest_ok in self._last_ingest_ok.items():
            tr = self.core.tracks.get(vid)
            if tr is None:
                continue
            one = fuse_tracks([tr], local, ORIGIN, self.core.cfg)
            if one.has_position:
                d, nis, _reason = should_use_measurement(local, ORIGIN, one, self.core.cfg)
                gate = d.name
            else:
                nis = 0.0
                gate = "TRACK"
            if not ingest_ok:
                gate = "REJECT"
            if self._bad_id == vid and self.bad_injected and result.decision == GateDecision.REJECT:
                gate = "REJECT"
                if result.nis > 0.0:
                    nis = result.nis
            event = LinkEvent(
                vehicle_id=vid,
                gate=gate,
                nis=nis,
                age_s=tr.state.age_s,
                pos_std_m=tr.state.pos_std_m,
                ttl=0.9,
            )
            if vid in by_id:
                self.links[by_id[vid]] = event
            else:
                by_id[vid] = len(self.links)
                self.links.append(event)

        b_err = math.hypot(self.baseline.n - n_true, self.baseline.e - e_true)
        v_err = math.hypot(self.v2x_ekf.n - n_true, self.v2x_ekf.e - e_true)
        self.error_history.append((self.t, b_err, v_err))
        if len(self.error_history) > 800:
            self.error_history = self.error_history[-800:]
        self.truth_path.append((e_true, n_true))
        self.baseline_path.append((self.baseline.e, self.baseline.n))
        self.v2x_path.append((self.v2x_ekf.e, self.v2x_ekf.n))
        for path in (self.truth_path, self.baseline_path, self.v2x_path):
            if len(path) > 2000:
                del path[: path.__len__() - 2000]

        frame = self.snapshot()
        self.t = round(self.t + dt, 6)
        self._step_count += 1
        if self.spec.demo_mode and self.t >= self.spec.duration_s:
            self.paused = True
        return frame

    def run_steps(self, n: int) -> DemoFrame:
        self.paused = False
        frame = self.snapshot()
        for _ in range(n):
            if self.paused:
                break
            frame = self.step()
        return frame

    def _v2x_status(self) -> str:
        if self.spec.n_remotes <= 0:
            return "NONE"
        high_loss = self.spec.packet_loss >= 0.20
        fused_reject = self.fused_decision == GateDecision.REJECT.name
        if high_loss or fused_reject or self.bad_injected:
            return "DEGRADED"
        return "ACTIVE"

    def _meas_status(self) -> str:
        d = self.fused_decision
        if d == GateDecision.ACCEPT.name:
            return "MEASUREMENT ACCEPTED"
        if d == GateDecision.DOWNWEIGHT.name:
            return "DOWNWEIGHTED"
        if d == GateDecision.REJECT.name:
            return "REJECTED"
        return "COOPERATIVE MEASUREMENT UNAVAILABLE"

    def _reject_info(self) -> tuple[float, str]:
        if self.fused_decision != GateDecision.REJECT.name:
            return 0.0, ""
        nis = self.fused_nis
        vid = ""
        rej = [lk for lk in self.links if lk.gate == "REJECT"]
        if rej:
            best = max(rej, key=lambda lk: lk.nis)
            vid = best.vehicle_id
            if best.nis > 0.0:
                nis = best.nis
        elif self._bad_id:
            vid = self._bad_id
        return nis, vid

    def snapshot(self) -> DemoFrame:
        n_true = EGO_SPEED_MPS * self.t
        e_true = 0.0
        vehicles = [
            VehicleView(
                vehicle_id="YOU",
                east_m=e_true,
                north_m=n_true,
                heading_rad=0.0,
                is_ego=True,
            )
        ]
        bad_id = getattr(self, "_bad_id", None)
        max_age = self.core.cfg.max_message_age_s
        for rem in self.sim.cfg.remotes:
            te, tn, _ve, _vn = truth_at(rem, self.t)
            heading = rem.heading_rad + rem.yaw_rate_rps * self.t
            tr = self.core.tracks.get(rem.vehicle_id)
            gate = "none"
            nis = 0.0
            age = 0.0
            std = rem.pos_std_m
            stale = True
            if tr is not None:
                std = tr.state.pos_std_m
                age = max(tr.state.age_s, self.t - tr.state.timestamp_s)
                stale = age > max_age
            for lk in self.links:
                if lk.vehicle_id == rem.vehicle_id:
                    gate = lk.gate
                    nis = lk.nis
                    age = lk.age_s
                    std = lk.pos_std_m
            vehicles.append(
                VehicleView(
                    vehicle_id=rem.vehicle_id,
                    east_m=te,
                    north_m=tn,
                    heading_rad=heading,
                    is_bad=(bad_id == rem.vehicle_id and self.bad_injected),
                    ingest_ok=self._last_ingest_ok.get(rem.vehicle_id, False),
                    gate=gate,
                    nis=nis,
                    age_s=age,
                    pos_std_m=std,
                    stale=stale,
                )
            )
        b_err = math.hypot(self.baseline.n - n_true, self.baseline.e - e_true)
        v_err = math.hypot(self.v2x_ekf.n - n_true, self.v2x_ekf.e - e_true)
        story_i = 0
        from .scenarios import RECORDING_TIMELINE

        for i, (ts, _) in enumerate(RECORDING_TIMELINE):
            if self.t + 1e-9 >= ts:
                story_i = i
        gnss_now = self.gnss_available()
        if not gnss_now and self.gnss_lost_at is None:
            start = self.spec.gnss_outage_s
            self.gnss_lost_at = start if start is not None and self.t + 1e-12 >= start else self.t
        gnss_banner = False
        if self.gnss_lost_at is not None and not gnss_now:
            gnss_banner = 0.0 <= (self.t - self.gnss_lost_at) < 3.5
        bad_banner = False
        if self.bad_event_at is not None:
            bad_banner = 0.0 <= (self.t - self.bad_event_at) < 4.0
        show_endcard = bool(self.spec.demo_mode and self.t + 1e-12 >= 40.0)
        reject_nis, reject_vid = self._reject_info()
        return DemoFrame(
            t=self.t,
            gnss_available=gnss_now,
            caption=caption_at(self.t) if self.spec.demo_mode else "",
            ego_truth_e=e_true,
            ego_truth_n=n_true,
            ego_heading=0.0,
            baseline_e=self.baseline.e,
            baseline_n=self.baseline.n,
            v2x_e=self.v2x_ekf.e,
            v2x_n=self.v2x_ekf.n,
            baseline_err_m=b_err,
            v2x_err_m=v_err,
            vehicles=vehicles,
            links=list(self.links),
            accepted=self.accepted,
            downweighted=self.downweighted,
            rejected=self.rejected_gate,
            ingest_rejected=self.core.health.rejected,
            validated=self.core.health.validated,
            received=self.core.health.received,
            n_remotes=self.spec.n_remotes,
            messages_this_step=self.messages_this_step,
            fused_age_s=self.fused_age_s,
            fused_nis=self.fused_nis,
            fused_decision=self.fused_decision,
            fused_reason=self.fused_reason,
            fused_contributors=self.fused_contributors,
            error_history=list(self.error_history),
            paused=self.paused,
            demo_mode=self.spec.demo_mode,
            story_index=story_i,
            gnss_banner=gnss_banner,
            bad_banner=bad_banner,
            show_endcard=show_endcard,
            v2x_status=self._v2x_status(),
            meas_status=self._meas_status(),
            reject_nis=reject_nis,
            reject_vehicle_id=reject_vid,
        )


def engine_from_name(name: str) -> DemoEngine:
    spec = SCENARIO_PRESETS[name]
    eng = DemoEngine(spec)
    eng.paused = True
    return eng
