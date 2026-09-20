from __future__ import annotations

from .types import GnssQuality, GnssSample


class GnssStateMachine:
    def __init__(self) -> None:
        self.forced_outage = False
        self._last_valid_t: float | None = None
        self.quality = GnssQuality.OUTAGE

    def reset(self) -> None:
        self.forced_outage = False
        self._last_valid_t = None
        self.quality = GnssQuality.OUTAGE

    def set_outage(self, on: bool) -> None:
        self.forced_outage = on

    def update(self, now: float, gnss: GnssSample | None, in_tunnel: bool) -> GnssQuality:
        if self.forced_outage or in_tunnel:
            self.quality = GnssQuality.OUTAGE
            return self.quality
        if gnss is None or not gnss.valid:
            if self._last_valid_t is None or (now - self._last_valid_t) > 2.0:
                self.quality = GnssQuality.OUTAGE
            else:
                self.quality = GnssQuality.DEGRADED
            return self.quality
        self._last_valid_t = gnss.timestamp
        if gnss.hdop > 3.5 or gnss.num_sats < 5:
            self.quality = GnssQuality.DEGRADED
        elif gnss.hdop > 2.2 or gnss.num_sats < 7:
            self.quality = GnssQuality.DEGRADED
        else:
            self.quality = GnssQuality.HEALTHY
        return self.quality

    def age(self, now: float) -> float:
        if self._last_valid_t is None:
            return 1e6
        return max(0.0, now - self._last_valid_t)
