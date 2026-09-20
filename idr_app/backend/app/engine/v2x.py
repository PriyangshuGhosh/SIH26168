from __future__ import annotations

import math

from .geo import LocalTangent
from .types import NavigationState


class V2XCoop:
    """MODE A software simulation only — not a radio."""

    def __init__(self, origin: LocalTangent) -> None:
        self.origin = origin
        self.enabled = True

    def measurement(self, t: float, nav: NavigationState, gt_x: float, gt_y: float):
        if not self.enabled:
            return "Unavailable", None
        # Simulated neighbor near ground-truth with noise
        phase = 0.35 * math.sin(t * 0.4)
        nx = gt_x + 12.0 * math.cos(phase)
        ny = gt_y + 8.0 * math.sin(phase)
        lat, lon = self.origin.to_ll(nx, ny)
        dx = nav.x - nx
        dy = nav.y - ny
        nis = (dx * dx + dy * dy) / 64.0
        if nis > 9.0:
            return "Reject", None
        if nis > 4.0:
            return "Downweight", (lat, lon, 80.0)
        return "Accept", (lat, lon, 25.0)
