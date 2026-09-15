from __future__ import annotations

import numpy as np
import pytest

from sih26168_alignment.frames import (
    orthonormal_error,
    quat_from_rotation_matrix,
    quat_rotate,
    rotation_det,
    rotation_matrix_from_quat,
    rotation_zyx,
)


@pytest.mark.parametrize("seed", range(25))
def test_random_orientation_invariants(seed: int):
    rng = np.random.default_rng(26168 + seed)
    ypr = rng.uniform(-np.pi, np.pi, size=3)
    R = rotation_zyx(*ypr)
    assert orthonormal_error(R) < 1e-9
    assert abs(rotation_det(R) - 1.0) < 1e-9
    q = quat_from_rotation_matrix(R)
    assert abs(np.linalg.norm(q) - 1.0) < 1e-12
    R2 = rotation_matrix_from_quat(q)
    assert np.allclose(R, R2, atol=1e-9)
    v = rng.normal(size=3)
    assert abs(np.linalg.norm(R @ v) - np.linalg.norm(v)) < 1e-12
    assert np.allclose(R.T @ (R @ v), v, atol=1e-12)
    assert np.allclose(quat_rotate(q, v), R @ v, atol=1e-9)
    # Gravity magnitude preserved
    g = np.array([0.0, 0.0, 9.80665])
    assert abs(np.linalg.norm(R @ g) - 9.80665) < 1e-12
