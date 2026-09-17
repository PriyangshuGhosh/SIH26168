"""Rotation augmentation and orientation-representation transforms for IMU windows.

The phone's mounting orientation is unknown and poorly covered by the training trips. All
functions here rotate the accelerometer and gyroscope of a window by the *same* rotation matrix
at every time step, which is exactly what a different rigid phone mounting would produce. Targets
are never touched.

Four augmentation/representation policies are compared in Milestone 3 (see
:func:`build_augmentation` and :func:`representation_transform`, and ``docs/experiments.md``):

* ``"none"``       -- no augmentation.
* ``"so3"``        -- full random SO(3) rotation (Milestone 2 default): robust to any mounting,
  including tilt, but this dataset's recordings all share one mounting tilt, so a model trained
  this way has to learn a harder invariance than this benchmark rewards.
* ``"yaw"``        -- random rotation about the vertical (gravity) axis only. Physically, the
  tilt of a dashboard/cupholder mount is fairly consistent for a given mounting style, but the
  heading a phone is dropped in at (its yaw about vertical) is arbitrary and carries no
  vehicle-forward information, so randomizing only yaw is a targeted, cheaper invariance to buy.
* ``"gravity_yaw"`` -- :func:`align_to_gravity` (deterministic, applied at train AND eval/inference
  time) followed by random yaw augmentation (train only). Where ``"yaw"`` asks the network to
  *learn* yaw-invariance from limited data, this policy removes the vertical axis analytically
  (it is directly computable from any causal window) and only randomizes yaw, so it should
  generalise to phones mounted at tilts never seen in training -- something ``"yaw"`` cannot do.

Only ``"none"``/``"so3"``/``"yaw"`` are augmentation-only (:func:`build_augmentation` returns a
function applied to training windows); ``"gravity_yaw"`` additionally requires the SAME
deterministic alignment at evaluation time, given by :func:`representation_transform`. Never apply
random augmentation (SO(3) or yaw) to validation or test data; the deterministic gravity alignment,
by contrast, must be applied identically at train and eval time when that policy is selected.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np


def random_rotation_matrices(n: int, rng: np.random.Generator, max_angle_deg: float = 180.0) -> np.ndarray:
    """Return ``(n, 3, 3)`` rotation matrices.

    ``max_angle_deg >= 180``: uniform (Haar) over SO(3) via random unit quaternions.
    Otherwise: uniformly random axis, angle uniform in ``[0, max_angle_deg]`` (Rodrigues).
    """
    if max_angle_deg >= 180.0:
        q = rng.standard_normal((n, 4))
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        w, x, y, z = q.T
        return np.stack([
            np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], axis=-1),
            np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], axis=-1),
            np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], axis=-1),
        ], axis=1)
    axis = rng.standard_normal((n, 3))
    axis /= np.linalg.norm(axis, axis=1, keepdims=True)
    theta = np.deg2rad(rng.uniform(0.0, max_angle_deg, size=n))
    k = np.zeros((n, 3, 3))
    k[:, 0, 1], k[:, 0, 2] = -axis[:, 2], axis[:, 1]
    k[:, 1, 0], k[:, 1, 2] = axis[:, 2], -axis[:, 0]
    k[:, 2, 0], k[:, 2, 1] = -axis[:, 1], axis[:, 0]
    s, c = np.sin(theta)[:, None, None], np.cos(theta)[:, None, None]
    return np.eye(3)[None] + s * k + (1 - c) * (k @ k)


def rotate_windows(windows: np.ndarray, rotations: np.ndarray) -> np.ndarray:
    """Apply per-window rotations to ``[B, T, 6]`` windows (acc = channels 0:3, gyr = 3:6)."""
    if windows.ndim != 3 or windows.shape[-1] != 6:
        raise ValueError(f"expected [B, T, 6], got {windows.shape}")
    r = rotations.astype(windows.dtype, copy=False)
    out = np.empty_like(windows)
    out[..., 0:3] = np.einsum("bij,btj->bti", r, windows[..., 0:3])
    out[..., 3:6] = np.einsum("bij,btj->bti", r, windows[..., 3:6])
    return out


def augment_so3(
    windows: np.ndarray,
    rng: np.random.Generator,
    probability: float = 1.0,
    max_angle_deg: float = 180.0,
) -> np.ndarray:
    """Randomly rotate each ``[B, T, 6]`` window with the given probability; returns a new array.

    Reproducible given the generator state (e.g. ``np.random.default_rng(seed)``).
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    b = windows.shape[0]
    rotations = random_rotation_matrices(b, rng, max_angle_deg)
    apply = rng.random(b) < probability
    rotations[~apply] = np.eye(3)
    return rotate_windows(windows, rotations)


def yaw_rotation_matrices(n: int, rng: np.random.Generator, max_angle_deg: float = 180.0) -> np.ndarray:
    """Return ``(n, 3, 3)`` rotations about the z axis (assumed vertical/gravity) only.

    Unlike :func:`random_rotation_matrices`, SO(2) is abelian, so a heading angle drawn uniformly
    from ``[-max_angle_deg, max_angle_deg]`` is already the Haar measure -- no special-casing at
    180 degrees is needed (it simply covers the full heading circle).
    """
    theta = np.deg2rad(rng.uniform(-max_angle_deg, max_angle_deg, size=n))
    c, s = np.cos(theta), np.sin(theta)
    r = np.zeros((n, 3, 3))
    r[:, 0, 0], r[:, 0, 1] = c, -s
    r[:, 1, 0], r[:, 1, 1] = s, c
    r[:, 2, 2] = 1.0
    return r


def augment_yaw(windows: np.ndarray, rng: np.random.Generator, probability: float = 1.0,
                max_angle_deg: float = 180.0) -> np.ndarray:
    """Randomly rotate each window about the vertical axis only (heading), with given probability.

    Preserves the window's tilt (pitch/roll relative to gravity) exactly; only randomizes which
    way the phone's "forward" edge points when it was placed down. See the module docstring.
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    b = windows.shape[0]
    rotations = yaw_rotation_matrices(b, rng, max_angle_deg)
    apply = rng.random(b) < probability
    rotations[~apply] = np.eye(3)
    return rotate_windows(windows, rotations)


def _skew(v: np.ndarray) -> np.ndarray:
    """``[..., 3]`` -> ``[..., 3, 3]`` skew-symmetric cross-product matrices."""
    z = np.zeros(v.shape[:-1])
    return np.stack([
        np.stack([z, -v[..., 2], v[..., 1]], axis=-1),
        np.stack([v[..., 2], z, -v[..., 0]], axis=-1),
        np.stack([-v[..., 1], v[..., 0], z], axis=-1),
    ], axis=-2)


def gravity_alignment_matrices(windows: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Per-window rotation mapping the window-mean accelerometer direction to ``+z``.

    The window's own mean accelerometer vector over its ``T`` samples is used as a cheap, causal
    estimate of "down" (gravity dominates typical vehicle linear acceleration in magnitude over a
    2-4 s window, the same simplification :mod:`src.models.baselines`' physics baseline makes).
    Only a window's own past/present samples are used, so this is causal and leakage-free: it can
    be computed identically at inference time from a live sensor stream. Windows whose mean
    acceleration is degenerate (near zero norm, or so close to exactly ``-z`` that the rotation
    axis is undefined) keep the identity rotation rather than an arbitrary/unstable one.
    """
    b = len(windows)
    acc_mean = windows[..., 0:3].astype(np.float64).mean(axis=1)
    norm = np.linalg.norm(acc_mean, axis=1)
    g_hat = np.zeros_like(acc_mean)
    ok_norm = norm > eps
    g_hat[ok_norm] = acc_mean[ok_norm] / norm[ok_norm, None]
    z = np.array([0.0, 0.0, 1.0])
    v = np.cross(g_hat, z[None, :])
    s = np.linalg.norm(v, axis=1)
    c = g_hat @ z
    r = np.tile(np.eye(3), (b, 1, 1))
    valid = ok_norm & (s > eps)
    k = _skew(v[valid])
    coeff = ((1.0 - c[valid]) / (s[valid] ** 2))[:, None, None]
    r[valid] = np.eye(3)[None] + k + k @ k * coeff
    return r


def align_to_gravity(windows: np.ndarray) -> np.ndarray:
    """Deterministically rotate each window so its estimated gravity direction points to ``+z``.

    Unlike the random augmentations above, this is applied identically at train AND eval/inference
    time when the ``"gravity_yaw"`` policy is selected (see :func:`representation_transform`).
    """
    return rotate_windows(windows, gravity_alignment_matrices(windows))


AugmentFn = Callable[[np.ndarray, np.random.Generator], np.ndarray]

AUGMENTATION_POLICIES: tuple[str, ...] = ("none", "so3", "yaw", "gravity_yaw")


def build_augmentation(policy: str, so3_cfg: dict, yaw_cfg: dict) -> AugmentFn | None:
    """Build the per-epoch training augmentation function for ``policy`` (see module docstring).

    Returns ``None`` for ``"none"`` (no augmentation applied). For ``"gravity_yaw"``, the returned
    function always applies the deterministic gravity alignment first (even to windows that end up
    not being yaw-rotated by ``yaw_cfg["probability"]``), so every training window that policy sees
    is gravity-aligned.
    """
    if policy == "none":
        return None
    if policy == "so3":
        return lambda w, rng: augment_so3(w, rng, so3_cfg["probability"], so3_cfg["max_angle_deg"])
    if policy == "yaw":
        return lambda w, rng: augment_yaw(w, rng, yaw_cfg["probability"], yaw_cfg["max_angle_deg"])
    if policy == "gravity_yaw":
        return lambda w, rng: augment_yaw(align_to_gravity(w), rng, yaw_cfg["probability"], yaw_cfg["max_angle_deg"])
    raise ValueError(f"unknown augmentation policy {policy!r}, expected one of {AUGMENTATION_POLICIES}")


def representation_transform(policy: str) -> Callable[[np.ndarray], np.ndarray]:
    """The deterministic transform paired with ``policy``, to be applied at BOTH train and eval time
    (in addition to whatever :func:`build_augmentation` does at train time only).

    Every policy except ``"gravity_yaw"`` leaves windows unchanged; ``"gravity_yaw"`` must align
    validation/test/inference windows to gravity exactly as it does for training windows, or the
    model would see a systematically different input distribution at evaluation time.
    """
    if policy not in AUGMENTATION_POLICIES:
        raise ValueError(f"unknown augmentation policy {policy!r}, expected one of {AUGMENTATION_POLICIES}")
    return align_to_gravity if policy == "gravity_yaw" else (lambda w: w)
