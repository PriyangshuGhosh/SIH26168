from dataclasses import dataclass
from enum import Enum


class NavigationMode(Enum):
    GNSS_AIDED = "GNSS_AIDED"
    DEAD_RECKONING = "DEAD_RECKONING"


@dataclass
class NavigationState:
    timestamp: float

    latitude: float
    longitude: float
    altitude: float

    vx: float
    vy: float

    yaw: float

    covariance: list

    mode: NavigationMode