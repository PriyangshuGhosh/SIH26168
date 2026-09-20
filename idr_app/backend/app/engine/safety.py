from __future__ import annotations

import math

from .geo import MAX_VEHICLE_SPEED_MPS, MIN_VARIANCE, SPEED_JUMP_MPS
from .types import SpeedEstimate


class SpeedValidityFilter:
    def __init__(self) -> None:
        self._last_valid: float | None = None
        self._last_t: float | None = None

    def reset(self) -> None:
        self._last_valid = None
        self._last_t = None

    def check(self, timestamp: float, velocity: float, variance: float) -> SpeedEstimate:
        if not math.isfinite(velocity) or not math.isfinite(variance):
            return SpeedEstimate(timestamp, 0.0, variance, False, "non_finite")
        if velocity < 0.0:
            return SpeedEstimate(timestamp, velocity, variance, False, "negative")
        if velocity > MAX_VEHICLE_SPEED_MPS:
            return SpeedEstimate(timestamp, velocity, variance, False, "impossible_speed")
        if variance < MIN_VARIANCE or not math.isfinite(variance):
            return SpeedEstimate(timestamp, velocity, variance, False, "variance_invalid")
        if self._last_valid is not None and self._last_t is not None:
            dt = timestamp - self._last_t
            if dt > 0 and abs(velocity - self._last_valid) / dt > SPEED_JUMP_MPS / 0.2:
                if abs(velocity - self._last_valid) > SPEED_JUMP_MPS:
                    return SpeedEstimate(timestamp, velocity, variance, False, "jump")
        self._last_valid = velocity
        self._last_t = timestamp
        return SpeedEstimate(timestamp, velocity, variance, True, "ok")
