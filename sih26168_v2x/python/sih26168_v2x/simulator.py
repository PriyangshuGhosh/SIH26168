from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field

from .frames import geo_to_local_enu, heading_speed_to_enu, local_enu_to_geo
from .types import (
    EnuOrigin,
    EnuVector,
    GeoPosition,
    MessageSource,
    MessageType,
    NormalizedV2XMessage,
    SecurityStatus,
    SourceQuality,
    TimestampPair,
)


@dataclass
class RemoteTruth:
    vehicle_id: str
    heading_rad: float = 0.0
    speed_mps: float = 15.0
    yaw_rate_rps: float = 0.0
    north0_m: float = 20.0
    east0_m: float = 0.0
    pos_std_m: float = 3.0
    vel_std_mps: float = 0.4
    gps_bias_east_m: float = 0.0


@dataclass
class SimConfig:
    seed: int = 1
    origin_lat: float = 12.9716
    origin_lon: float = 77.5946
    origin_alt: float = 920.0
    dt_s: float = 0.1
    packet_loss: float = 0.0
    latency_mean_s: float = 0.05
    latency_jitter_s: float = 0.01
    out_of_order_rate: float = 0.0
    duplicate_rate: float = 0.0
    bad_message_rate: float = 0.0
    timestamp_error_s: float = 0.0
    remotes: list[RemoteTruth] = field(default_factory=list)


SCENARIOS = {
    "straight": lambda: SimConfig(remotes=[RemoteTruth("lead", 0.0, 16.0, 0.0, 25.0, 0.0)]),
    "curved": lambda: SimConfig(remotes=[RemoteTruth("lead", 0.2, 14.0, 0.05, 20.0, 4.0)]),
    "highway": lambda: SimConfig(remotes=[RemoteTruth(f"h{i}", 0.0, 25.0, 0.0, 30.0 + 8 * i, 3.5 * (i - 1))
                                          for i in range(3)]),
    "urban": lambda: SimConfig(remotes=[RemoteTruth("u1", 0.4, 8.0, 0.02, 15.0, -6.0)]),
    "intersection": lambda: SimConfig(remotes=[
        RemoteTruth("n", 0.0, 10.0, 0.0, 40.0, 0.0),
        RemoteTruth("e", math.pi / 2, 10.0, 0.0, 0.0, 40.0),
    ]),
    "convoy": lambda: SimConfig(remotes=[RemoteTruth(f"c{i}", 0.0, 16.0, 0.0, 12.0 + 8 * i, 0.0)
                                         for i in range(4)]),
    "overtaking": lambda: SimConfig(remotes=[RemoteTruth("slow", 0.0, 12.0, 0.0, 18.0, 0.0),
                                             RemoteTruth("fast", 0.0, 22.0, 0.0, 8.0, 3.5)]),
    "lane_change": lambda: SimConfig(remotes=[RemoteTruth("lc", 0.05, 15.0, 0.03, 20.0, 0.0)]),
    "braking": lambda: SimConfig(remotes=[RemoteTruth("brk", 0.0, 6.0, 0.0, 18.0, 0.0)]),
    "acceleration": lambda: SimConfig(remotes=[RemoteTruth("acc", 0.0, 20.0, 0.0, 22.0, 0.0)]),
    "sparse": lambda: SimConfig(remotes=[RemoteTruth("s", 0.0, 15.0, 0.0, 40.0, -10.0)]),
    "dense": lambda: SimConfig(remotes=[RemoteTruth(f"d{i}", 0.0, 14.0 + i * 0.2, 0.0, 10.0 + 6 * i,
                                                    (i % 3) * 3.5 - 3.5) for i in range(10)]),
}


def scenario(name: str, **overrides) -> SimConfig:
    cfg = SCENARIOS[name]()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def truth_at(remote: RemoteTruth, t: float) -> tuple[float, float, float, float]:
    heading = remote.heading_rad + remote.yaw_rate_rps * t
    ve, vn = heading_speed_to_enu(heading, remote.speed_mps)
    east = remote.east0_m + ve * t
    north = remote.north0_m + vn * t
    return east, north, ve, vn


class V2XSimulator:
    """Broadcasts remote *estimates*, never ego ground truth."""

    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.origin = EnuOrigin(cfg.origin_lat, cfg.origin_lon, cfg.origin_alt, True)

    def messages_at(self, t: float) -> list[NormalizedV2XMessage]:
        out: list[NormalizedV2XMessage] = []
        for rem in self.cfg.remotes:
            if self.rng.random() < self.cfg.packet_loss:
                continue
            te, tn, ve, vn = truth_at(rem, t)
            # Remote's own GNSS-like estimate (noisy), not truth.
            ee = te + rem.gps_bias_east_m + self.rng.gauss(0.0, rem.pos_std_m)
            nn = tn + self.rng.gauss(0.0, rem.pos_std_m)
            ve_b = ve + self.rng.gauss(0.0, rem.vel_std_mps)
            vn_b = vn + self.rng.gauss(0.0, rem.vel_std_mps)
            geo = local_enu_to_geo(EnuVector(ee, nn, 0.0), self.origin)
            if self.rng.random() < self.cfg.bad_message_rate:
                geo.latitude_deg = 1.0e9
            latency = self.cfg.latency_mean_s + self.rng.gauss(0.0, self.cfg.latency_jitter_s)
            sender = t - latency - self.cfg.timestamp_error_s
            if self.rng.random() < self.cfg.out_of_order_rate:
                sender -= 1.0
            msg = NormalizedV2XMessage(
                vehicle_id=rem.vehicle_id,
                time=TimestampPair(sender_time_s=sender, receive_time_s=t),
                geo=geo,
                velocity_enu=EnuVector(ve_b, vn_b, 0.0),
                heading_rad=rem.heading_rad + rem.yaw_rate_rps * t,
                message_type=MessageType.CAM_LIKE,
                source=MessageSource.SIMULATOR,
                quality=SourceQuality.MEDIUM,
                declared_security=SecurityStatus.UNVERIFIED,
                declared_pos_std_m=rem.pos_std_m,
                declared_vel_std_mps=rem.vel_std_mps,
            )
            out.append(msg)
            if self.rng.random() < self.cfg.duplicate_rate:
                out.append(msg)
        return out

    def write_jsonl(self, path: str, t_end: float) -> None:
        with open(path, "w", encoding="utf-8") as f:
            t = 0.0
            while t <= t_end + 1e-9:
                for m in self.messages_at(t):
                    f.write(json.dumps(_msg_dict(m)) + "\n")
                t += self.cfg.dt_s


def _msg_dict(m: NormalizedV2XMessage) -> dict:
    return {
        "vehicle_id": m.vehicle_id,
        "sender_time_s": m.time.sender_time_s,
        "receive_time_s": m.time.receive_time_s,
        "clock_offset_s": m.time.clock_offset_s,
        "latitude_deg": m.geo.latitude_deg,
        "longitude_deg": m.geo.longitude_deg,
        "altitude_m": m.geo.altitude_m,
        "ve_mps": m.velocity_enu.east_m,
        "vn_mps": m.velocity_enu.north_m,
        "vu_mps": m.velocity_enu.up_m,
        "heading_rad": m.heading_rad,
        "declared_pos_std_m": m.declared_pos_std_m,
        "declared_vel_std_mps": m.declared_vel_std_mps,
        "source": "simulator",
        "quality": "medium",
        "security": "unverified",
        "message_type": "cam_like",
    }


def parse_jsonl_line(line: str) -> NormalizedV2XMessage | None:
    line = line.strip()
    if not line or line[0] != "{":
        return None
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return None
    if "vehicle_id" not in d:
        return None
    m = NormalizedV2XMessage()
    m.vehicle_id = str(d.get("vehicle_id", ""))
    m.time.sender_time_s = float(d.get("sender_time_s", 0.0))
    m.time.receive_time_s = float(d.get("receive_time_s", 0.0))
    m.time.clock_offset_s = float(d.get("clock_offset_s", 0.0))
    m.geo = GeoPosition(float(d.get("latitude_deg", 0.0)), float(d.get("longitude_deg", 0.0)),
                        float(d.get("altitude_m", 0.0)))
    m.velocity_enu = EnuVector(float(d.get("ve_mps", 0.0)), float(d.get("vn_mps", 0.0)),
                               float(d.get("vu_mps", 0.0)))
    m.heading_rad = float(d.get("heading_rad", 0.0))
    m.declared_pos_std_m = float(d.get("declared_pos_std_m", 5.0))
    m.declared_vel_std_mps = float(d.get("declared_vel_std_mps", 1.0))
    m.source = MessageSource.REPLAY
    return m
