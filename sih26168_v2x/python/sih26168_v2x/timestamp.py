from __future__ import annotations

import math
from dataclasses import dataclass

from .types import TimestampPair


@dataclass
class MessageTiming:
    message_age_s: float = 0.0
    estimated_event_time_s: float = 0.0
    stale: bool = False
    out_of_order: bool = False
    duplicate: bool = False


def evaluate_timing(time: TimestampPair, last_sender_time_s: float, max_age_s: float,
                    min_dt_s: float) -> MessageTiming:
    out = MessageTiming()
    if not all(math.isfinite(x) for x in (time.sender_time_s, time.receive_time_s, time.clock_offset_s)):
        out.stale = True
        out.message_age_s = max_age_s + 1.0
        return out
    out.message_age_s = time.receive_time_s - time.sender_time_s - time.clock_offset_s
    out.estimated_event_time_s = time.receive_time_s - out.message_age_s
    if not math.isfinite(out.message_age_s) or out.message_age_s > max_age_s or out.message_age_s < -0.25:
        out.stale = True
    if last_sender_time_s >= 0.0:
        ds = time.sender_time_s - last_sender_time_s
        if abs(ds) < min_dt_s:
            out.duplicate = True
        elif ds < 0.0:
            out.out_of_order = True
    return out


def age_inflation_scale(age_s: float, time_constant_s: float) -> float:
    if not math.isfinite(age_s) or age_s <= 0.0:
        return 1.0
    tau = max(time_constant_s, 1e-6)
    r = age_s / tau
    return math.sqrt(1.0 + r * r)


def time_sync_position_std_m(clock_offset_std_s: float, speed_mps: float) -> float:
    if not math.isfinite(clock_offset_std_s) or not math.isfinite(speed_mps):
        return 1.0e3
    return abs(clock_offset_std_s) * abs(speed_mps)
