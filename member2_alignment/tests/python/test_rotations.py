from __future__ import annotations

import math

import numpy as np
import pytest

from sih26168_alignment.frames import (
    orthonormal_error,
    phoneToVehicleVector,
    quat_conjugate,
    quat_from_rotation_matrix,
    quat_identity,
    quat_multiply,
    quat_normalize,
    quat_rotate,
    quatPhoneToVehicle,
    rotation_det,
    rotation_gravity_up_to_vehicle_z,
    rotation_matrix_from_quat,
    rotation_x,
    rotation_y,
    rotation_z,
    rotation_zyx,
    vehicleToPhoneVector,
)


def test_identity_rotation():
    R = np.eye(3)
    v = np.array([1.0, 2.0, 3.0])
    assert np.allclose(phoneToVehicleVector(R, v), v)
    assert np.allclose(quat_rotate(quat_identity(), v), v)


@pytest.mark.parametrize(
    "axis_fn,angle,src,dst",
    [
        (rotation_z, math.pi / 2, np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
        (rotation_z, -math.pi / 2, np.array([1.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0])),
        (rotation_x, math.pi / 2, np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
        (rotation_x, -math.pi / 2, np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, -1.0])),
        (rotation_y, math.pi / 2, np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0])),
        (rotation_y, -math.pi / 2, np.array([0.0, 0.0, 1.0]), np.array([-1.0, 0.0, 0.0])),
    ],
)
def test_principal_rotations(axis_fn, angle, src, dst):
    R = axis_fn(angle)
    assert np.allclose(R @ src, dst, atol=1e-9)


def test_combined_zyx_roundtrip():
    R = rotation_zyx(0.4, -0.7, 1.1)
    v = np.array([0.3, -1.2, 0.5])
    assert np.allclose(R.T @ (R @ v), v)
    q = quat_from_rotation_matrix(R)
    assert np.allclose(rotation_matrix_from_quat(q), R, atol=1e-9)
    assert np.allclose(quat_rotate(q, v), R @ v, atol=1e-9)


def test_quat_normalize_and_inverse():
    q = quat_normalize(np.array([0.2, -0.4, 0.1, 0.7]))
    assert abs(np.linalg.norm(q) - 1.0) < 1e-12
    assert q[0] >= 0.0
    inv = quat_conjugate(q)
    prod = quat_multiply(inv, q)
    assert np.allclose(prod, quat_identity(), atol=1e-12)


def test_gravity_maps_to_up():
    g_up = np.array([0.2, -0.5, 0.8])
    g_up = g_up / np.linalg.norm(g_up)
    R = rotation_gravity_up_to_vehicle_z(g_up)
    mapped = R @ g_up
    assert np.allclose(mapped, np.array([0.0, 0.0, 1.0]), atol=1e-9)
    assert orthonormal_error(R) < 1e-9
    assert abs(rotation_det(R) - 1.0) < 1e-9


def test_forward_left_up_basis():
    R = np.eye(3)
    assert np.allclose(phoneToVehicleVector(R, [1, 0, 0]), [1, 0, 0])
    assert np.allclose(phoneToVehicleVector(R, [0, 1, 0]), [0, 1, 0])
    assert np.allclose(phoneToVehicleVector(R, [0, 0, 1]), [0, 0, 1])


def test_frame_inversion_caught():
    R = rotation_zyx(0.9, -0.4, 0.2)
    a_p = np.array([1.0, -2.0, 3.0])
    a_v = phoneToVehicleVector(R, a_p)
    a_p2 = vehicleToPhoneVector(R, a_v)
    assert np.allclose(a_p, a_p2, atol=1e-12)
    q = quatPhoneToVehicle(R)
    assert np.allclose(quat_rotate(q, a_p), a_v, atol=1e-9)
    # Inverse mapping must NOT equal the forward mapping for this R.
    assert np.linalg.norm(a_v - a_p) > 0.5


def test_quaternion_multiply_order():
    qz = quat_from_rotation_matrix(rotation_z(0.3))
    qy = quat_from_rotation_matrix(rotation_y(-0.2))
    R = rotation_z(0.3) @ rotation_y(-0.2)
    q = quat_multiply(qz, qy)
    v = np.array([0.4, 0.1, -0.7])
    assert np.allclose(quat_rotate(q, v), R @ v, atol=1e-9)
    q_wrong = quat_multiply(qy, qz)
    assert np.linalg.norm(quat_rotate(q_wrong, v) - R @ v) > 1e-3
