from __future__ import annotations

from .types import VisionDecision


class VisionAid:
    """Confidence-gated visual motion. Not a metric depth localizer."""

    def __init__(self) -> None:
        self.enabled = True

    def evaluate(self, in_tunnel: bool, speed: float, texture: float) -> tuple[VisionDecision, float, float, float]:
        """Returns decision, quality, dx, dy (ENU visual displacement suggestion)."""
        if not self.enabled:
            return VisionDecision.UNAVAILABLE, 0.0, 0.0, 0.0
        quality = texture
        if in_tunnel:
            quality *= 0.12
        if speed < 0.4:
            quality *= 0.5
        if quality >= 0.62:
            return VisionDecision.ACCEPT, quality, 0.0, 0.0
        if quality >= 0.28:
            return VisionDecision.DOWNWEIGHT, quality, 0.0, 0.0
        return VisionDecision.REJECT, quality, 0.0, 0.0
