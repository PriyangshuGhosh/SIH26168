"""NumPy reference for Member 3 GNSS position/speed gating.

This module complements reference_ekf.py with the 2-D GNSS position update,
HDOP-to-metre uncertainty convention, scalar GNSS speed update and NIS gates.
"""

import math
import numpy as np


EARTH_RADIUS_M = 6378137.0
GNSS_POSITION_NIS_THRESHOLD = 5.991
SPEED_NIS_THRESHOLD = 3.841
POSITION_SIGMA_FLOOR_M = 1.0
HDOP_TO_SIGMA_M = 5.0
SPEED_VARIANCE_FLOOR_M2S2 = 0.25


def local_position(latitude, longitude, reference_latitude, reference_longitude):
    """Convert WGS84 degrees to a vehicle-scale local North/East approximation."""
    lat0 = math.radians(reference_latitude)
    north = math.radians(latitude - reference_latitude) * EARTH_RADIUS_M
    east = (math.radians(longitude - reference_longitude) * EARTH_RADIUS_M *
            math.cos(lat0))
    return np.array([north, east], dtype=float)


def position_nis(state_position, covariance, measured_position, hdop):
    """Return the 2-D GNSS position NIS using the production uncertainty model."""
    sigma = max(POSITION_SIGMA_FLOOR_M, hdop * HDOP_TO_SIGMA_M)
    R = np.eye(2) * sigma**2
    H = np.zeros((2, 8))
    H[0, 0] = H[1, 1] = 1.0
    innovation = (np.asarray(measured_position, dtype=float) -
                  np.asarray(state_position, dtype=float))
    S = H @ covariance @ H.T + R
    solved = np.linalg.solve(S, innovation)
    return float(innovation @ solved)


def speed_nis(vx, covariance, measured_speed, variance):
    """Return scalar forward-speed NIS."""
    H = np.zeros((1, 8))
    H[0, 2] = 1.0
    R = max(float(variance), 1e-4)
    innovation = float(measured_speed) - float(vx)
    S = (H @ covariance @ H.T).item() + R
    return innovation * innovation / S


if __name__ == "__main__":
    P = np.diag([25.0, 25.0, 4.0, 4.0, math.pi**2, 0.25, 0.25, 0.25])
    p = local_position(17.3851, 78.4868, 17.385, 78.4867)
    assert np.isfinite(p).all()
    assert position_nis(np.zeros(2), P, np.zeros(2), 1.0) == 0.0
    assert speed_nis(5.0, P, 5.0, SPEED_VARIANCE_FLOOR_M2S2) == 0.0
    print("NumPy Member 3 GNSS reference smoke test passed.")
