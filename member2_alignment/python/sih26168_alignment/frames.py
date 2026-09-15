"""Coordinate-frame mathematics for phone (p) and vehicle (v).

Conventions
-----------
Vehicle frame v (right-handed):
    +X forward, +Y left, +Z up.

Phone frame p:
    the IMU's native right-handed axes. Arbitrary relative to the vehicle.

Rotation
--------
``R_vp`` is the 3x3 DCM that maps *coordinate representations*:

    a_v = R_vp @ a_p
    omega_v = R_vp @ omega_p

``q_pv`` is the Hamilton quaternion ``[w, x, y, z]`` of that same mapping:
vector rotation from phone to vehicle:

    v_v = q_pv ⊗ v_p ⊗ q_pv*

so ``quatPhoneToVehicle()`` ≡ ``q_pv``.  The inverse ``q_vp = q_pv*`` maps
vehicle vectors into the phone frame.

These are *passive* changes of coordinates for the same physical vector
(equivalently, the active rotation taking the phone basis onto the vehicle
basis). Matrices are applied on the left to column vectors. Composition is
``R_ac = R_ab @ R_bc``. Inverse is transpose for rotations / conjugate for
unit quaternions.

Gravity / accelerometer: the IMU reports specific force ``f = a_linear - g``.
With ``g_v = [0, 0, -g]`` (Z up), a stationary device reads ``f_v ≈ [0, 0, +g]``.
"""

from __future__ import annotations

import numpy as np

QUAT_WXYZ = ("w", "x", "y", "z")
G_STANDARD = 9.80665


def _as_vec3(v: np.ndarray) -> np.ndarray:
    out = np.asarray(v, dtype=float).reshape(3)
    return out


def _as_quat(q: np.ndarray) -> np.ndarray:
    return np.asarray(q, dtype=float).reshape(4)


def is_finite_vec(v: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(v)))


def vector_norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(_as_vec3(v)))


def safe_normalize(v: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    x = _as_vec3(v)
    n = float(np.linalg.norm(x))
    if n < eps:
        return np.zeros(3)
    return x / n


def quat_identity() -> np.ndarray:
    return np.array([1.0, 0.0, 0.0, 0.0])


def quat_normalize(q: np.ndarray, eps: float = 1e-15) -> np.ndarray:
    q = _as_quat(q)
    n = float(np.linalg.norm(q))
    if n < eps:
        return quat_identity()
    q = q / n
    if q[0] < 0.0:
        q = -q
    return q


def quat_conjugate(q: np.ndarray) -> np.ndarray:
    q = _as_quat(q)
    return np.array([q[0], -q[1], -q[2], -q[3]])


def quat_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Hamilton product q1 ⊗ q2 (apply q2 first)."""
    w1, x1, y1, z1 = _as_quat(q1)
    w2, x2, y2, z2 = _as_quat(q2)
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


def quat_rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate vector v by unit quaternion q (Hamilton)."""
    q = quat_normalize(q)
    w, x, y, z = q
    vx, vy, vz = _as_vec3(v)
    # Standard optimized form equivalent to q ⊗ [0,v] ⊗ q*
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return np.array(
        [
            vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx),
        ]
    )


def rotation_matrix_from_quat(q: np.ndarray) -> np.ndarray:
    q = quat_normalize(q)
    w, x, y, z = q
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ]
    )


def quat_from_rotation_matrix(R: np.ndarray) -> np.ndarray:
    """Shepperd's method; returns [w, x, y, z] with w >= 0."""
    R = np.asarray(R, dtype=float).reshape(3, 3)
    t = float(np.trace(R))
    if t > 0.0:
        s = np.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return quat_normalize(np.array([w, x, y, z]))


def rotation_z(yaw: float) -> np.ndarray:
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rotation_y(pitch: float) -> np.ndarray:
    c, s = np.cos(pitch), np.sin(pitch)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rotation_x(roll: float) -> np.ndarray:
    c, s = np.cos(roll), np.sin(roll)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rotation_zyx(yaw: float, pitch: float, roll: float) -> np.ndarray:
    """Intrinsic ZYX: R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    return rotation_z(yaw) @ rotation_y(pitch) @ rotation_x(roll)


def rotation_gravity_up_to_vehicle_z(g_up_p: np.ndarray) -> np.ndarray:
    """Build a deterministic tilt DCM ``R_gp`` such that ``R_gp @ g_up_p = [0,0,1]``.

    Remaining yaw about Z is *not* the vehicle heading; it is a canonical
    gauge choice so that roll/pitch can be applied before yaw is observed.
    """
    z = safe_normalize(g_up_p)
    if vector_norm(z) < 1e-9:
        return np.eye(3)
    ref = np.array([1.0, 0.0, 0.0]) if abs(z[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    y = np.cross(z, ref)
    yn = vector_norm(y)
    if yn < 1e-9:
        ref = np.array([0.0, 0.0, 1.0])
        y = np.cross(z, ref)
        yn = vector_norm(y)
        if yn < 1e-9:
            return np.eye(3)
    y = y / yn
    x = np.cross(y, z)
    x = safe_normalize(x)
    return np.stack([x, y, z], axis=0)


def phoneToVehicleVector(R_vp: np.ndarray, vec_p: np.ndarray) -> np.ndarray:
    return np.asarray(R_vp, dtype=float).reshape(3, 3) @ _as_vec3(vec_p)


def vehicleToPhoneVector(R_vp: np.ndarray, vec_v: np.ndarray) -> np.ndarray:
    return np.asarray(R_vp, dtype=float).reshape(3, 3).T @ _as_vec3(vec_v)


def quatPhoneToVehicle(R_vp: np.ndarray) -> np.ndarray:
    return quat_from_rotation_matrix(R_vp)


def quatVehicleToPhone(R_vp: np.ndarray) -> np.ndarray:
    return quat_conjugate(quat_from_rotation_matrix(R_vp))


def rotationMatrixPhoneToVehicle(
    g_up_p: np.ndarray | None, yaw_rad: float | None
) -> np.ndarray:
    if g_up_p is None:
        return np.eye(3)
    R_gp = rotation_gravity_up_to_vehicle_z(g_up_p)
    if yaw_rad is None:
        return R_gp
    return rotation_z(yaw_rad) @ R_gp


def orthonormal_error(R: np.ndarray) -> float:
    R = np.asarray(R, dtype=float).reshape(3, 3)
    return float(np.linalg.norm(R.T @ R - np.eye(3), ord="fro"))


def rotation_det(R: np.ndarray) -> float:
    return float(np.linalg.det(np.asarray(R, dtype=float).reshape(3, 3)))
