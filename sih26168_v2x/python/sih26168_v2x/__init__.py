"""MODE A software-simulation V2X / cooperative localization (Python oracle)."""

from .core import V2XCore
from .frames import geo_to_local_enu, heading_speed_to_enu, local_enu_to_geo, vehicle_frame_to_navigation_enu
from .types import (
    CHI2_DOF2_P95,
    CHI2_DOF2_P99,
    EARTH_RADIUS_M,
    GateDecision,
    LocalNavigationState,
    NormalizedV2XMessage,
)

__all__ = [
    "V2XCore",
    "NormalizedV2XMessage",
    "LocalNavigationState",
    "GateDecision",
    "geo_to_local_enu",
    "local_enu_to_geo",
    "vehicle_frame_to_navigation_enu",
    "heading_speed_to_enu",
    "EARTH_RADIUS_M",
    "CHI2_DOF2_P95",
    "CHI2_DOF2_P99",
]
