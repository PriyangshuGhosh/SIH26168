from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from conftest import SESSIONS, SPLIT_RULES, make_arrays
from src.data.augmentation import (
    AUGMENTATION_POLICIES, align_to_gravity, augment_so3, augment_yaw, build_augmentation, gravity_alignment_matrices,
    random_rotation_matrices, representation_transform, rotate_windows, yaw_rotation_matrices,
)
from src.data.dataset import IMU_CHANNELS, LeakageError, build_model_input, check_input_keys, from_arrays, load_npz
from src.data.inspect_dataset import forbidden_keys_present, inspect, validate
from src.data.splits import assert_no_group_leakage, lovo_folds, make_split, trip_family
from src.data.windowing import assert_windows_valid, gather_windows, seconds_to_samples, window_end_indices

REAL_NPZ = Path(__file__).resolve().parents[1] / "data" / "member1_imu_speed.npz"


# ----------------------------------------------------------------------------- loading / leakage

def test_npz_loading(npz_path, arrays):
    ds = load_npz(npz_path)
    n = len(arrays["target_speed_mps"])
    assert ds.imu.shape == (n, 6) and ds.imu.dtype == np.float32
    np.testing.assert_array_equal(ds.imu[:, :3], arrays["acc"])
    np.testing.assert_array_equal(ds.imu[:, 3:], arrays["gyr"])
    assert len(IMU_CHANNELS) == 6


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_npz(tmp_path / "nope.npz")


def test_missing_required_key_raises(arrays):
    del arrays["gyr"]
    with pytest.raises(KeyError):
        from_arrays(arrays)


def test_kmh_target_is_converted(arrays):
    kmh = dict(arrays, target_speed_mps=arrays["target_speed_mps"] * 3.6)
    np.testing.assert_allclose(from_arrays(kmh, target_units="km/h").target, arrays["target_speed_mps"], rtol=1e-5)


def test_wrong_imu_dimension_rejected(arrays):
    with pytest.raises(ValueError):
        build_model_input(dict(arrays, acc=arrays["acc"][:, :2]))


@pytest.mark.parametrize("key", [
    "veh_speed", "veh_yaw_rate", "wheel_speed_fl", "heading", "indicated_speed", "gps_lat", "gps_lon", "lat", "lon",
    "gps_speed", "gps_accuracy", "orientation", "mag", "magnetometer", "trip_id", "session_id", "date", "timestamp",
    "t_session_s", "has_ground_truth", "gps_outage", "target_speed_mps", "verdict", "sample_idx",
])
def test_forbidden_input_keys_rejected(key):
    with pytest.raises(LeakageError):
        check_input_keys(["acc", "gyr", key])


def test_extra_fields_never_reach_model_input(arrays):
    polluted = dict(arrays, veh_speed=arrays["target_speed_mps"], gps_speed=arrays["target_speed_mps"],
                    mag=np.ones_like(arrays["acc"]))
    ds = from_arrays(polluted)
    assert ds.imu.shape[1] == 6
    np.testing.assert_array_equal(ds.imu, np.concatenate([arrays["acc"], arrays["gyr"]], axis=1))
    assert set(forbidden_keys_present(list(polluted))) >= {"veh_speed", "gps_speed", "mag"}


def test_validation_and_inspection(npz_path, arrays):
    ds = from_arrays(arrays)
    assert validate(arrays, ds) == []
    report = inspect(npz_path)
    assert report["errors"] == [] and report["n_sessions"] == len(SESSIONS)
    assert abs(report["sampling"]["estimated_rate_hz"] - 10.0) < 1e-3
    bad = dict(arrays, acc=arrays["acc"].copy())
    bad["acc"][3, 0] = np.nan
    assert any("non-finite IMU" in e for e in validate(bad, from_arrays(bad)))


# ----------------------------------------------------------------------------- windowing

def test_seconds_to_samples():
    assert seconds_to_samples(2.0) == 20 and seconds_to_samples(4.0) == 40


@pytest.mark.parametrize("window,stride", [(20, 5), (40, 5), (20, 1), (40, 1)])
def test_window_shape_and_counts(arrays, window, stride):
    ds = from_arrays(arrays)
    ends = window_end_indices(ds, window, stride)
    expected = sum(len(range(window - 1, n, stride)) for _, n in SESSIONS.values() if n >= window)
    assert len(ends) == expected
    w = gather_windows(ds.imu, ends, window)
    assert w.shape == (len(ends), window, 6) and w.dtype == np.float32
    assert_windows_valid(ds, ends, window)


def test_windows_never_cross_sessions(arrays):
    ds = from_arrays(arrays)
    ends = window_end_indices(ds, 40, 1)
    first = ends - 39
    assert np.all(ds.session_id[first] == ds.session_id[ends])
    # the first valid window of each session ends exactly 39 rows after the session start
    for sid in SESSIONS:
        rows = np.flatnonzero(ds.session_id == sid)
        sess_ends = ends[np.isin(ends, rows)]
        assert sess_ends.min() == rows[0] + 39 and sess_ends.max() == rows[-1]


def test_session_boundary_enforced_even_if_counters_continue(arrays):
    """Session id alone must stop a window, even when sample_idx and time run on seamlessly."""
    arrays = dict(arrays, sample_idx=np.arange(len(arrays["sample_idx"])),
                  t_session_s=(np.arange(len(arrays["sample_idx"])) * 0.1).astype(np.float32))
    ds = from_arrays(arrays)
    for window, stride in ((20, 1), (40, 1), (20, 5)):
        ends = window_end_indices(ds, window, stride)
        assert np.all(ds.session_id[ends - window + 1] == ds.session_id[ends])
        expected = sum(len(range(window - 1, n, stride)) for _, n in SESSIONS.values() if n >= window)
        assert len(ends) == expected


def test_windows_are_causal(arrays):
    """Window content and label for end e depend only on rows <= e."""
    ds = from_arrays(arrays)
    ends = window_end_indices(ds, 20, 1)
    e = int(ends[len(ends) // 2])
    before = gather_windows(ds.imu, np.array([e]), 20)
    np.testing.assert_array_equal(before[0], ds.imu[e - 19:e + 1])
    changed = dict(arrays, acc=arrays["acc"].copy(), gyr=arrays["gyr"].copy())
    changed["acc"][e + 1:] += 100.0
    changed["gyr"][e + 1:] -= 100.0
    ds2 = from_arrays(changed)
    np.testing.assert_array_equal(gather_windows(ds2.imu, np.array([e]), 20), before)


def test_invalid_samples_and_gaps_rejected(arrays):
    arrays = dict(arrays, gyr=arrays["gyr"].copy(), sample_idx=arrays["sample_idx"].copy(),
                  target_speed_mps=arrays["target_speed_mps"].copy())
    arrays["gyr"][50, 1] = np.inf                  # inside Vw2__s00 (rows 0..119)
    arrays["sample_idx"][100:120] += 5             # gap between rows 99 and 100
    arrays["target_speed_mps"][119] = np.nan       # label missing at a prediction point
    ds = from_arrays(arrays)
    ends = window_end_indices(ds, 20, 1)
    in_first = ends[ends < 120]
    assert not np.any((in_first - 19 <= 50) & (in_first >= 50)), "window containing non-finite IMU accepted"
    assert not np.any((in_first - 19 <= 99) & (in_first >= 100)), "window spanning a sample_idx gap accepted"
    assert 119 not in in_first
    assert_windows_valid(ds, ends, 20)


def test_time_step_gap_rejected(arrays):
    arrays = dict(arrays, t_session_s=arrays["t_session_s"].copy())
    arrays["t_session_s"][60:120] += 1.0
    ends = window_end_indices(from_arrays(arrays), 20, 1)
    assert not np.any((ends < 120) & (ends - 19 <= 59) & (ends >= 60))


# ----------------------------------------------------------------------------- splits

def test_split_membership(arrays):
    split = make_split(arrays["trip_id"], arrays["session_id"], SPLIT_RULES)
    assert split.trips == {"train": ["Vfa02", "Vw2", "Vw4"], "val": ["M"], "test": ["S1", "S3a"]}
    assert split.unassigned_trips == ["Vfa01", "Y1"]
    assert split.sessions["val"] == ["M__s01", "M__s02"]


def test_no_group_leakage(arrays):
    split = make_split(arrays["trip_id"], arrays["session_id"], SPLIT_RULES)
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        assert not np.any(split.masks[a] & split.masks[b])
        assert not set(arrays["session_id"][split.masks[a]]) & set(arrays["session_id"][split.masks[b]])
        assert not set(arrays["trip_id"][split.masks[a]]) & set(arrays["trip_id"][split.masks[b]])


def test_leakage_detected():
    with pytest.raises(ValueError):  # a trip matching two splits
        make_split(np.array(["Vw2", "M"]), np.array(["a", "b"]), {"train": ["Vw2", "M"], "val": ["M"], "test": []})
    with pytest.raises(AssertionError):  # same family in train and test
        make_split(np.array(["Vfa02", "Vfa01"]), np.array(["a", "b"]), {"train": ["Vfa02"], "val": [], "test": ["Vfa01"]})
    split = make_split(np.array(["Vw2", "M"]), np.array(["x", "y"]), {"train": ["Vw2"], "val": ["M"], "test": []})
    with pytest.raises(AssertionError):  # a session id shared across splits
        assert_no_group_leakage(split, np.array(["Vw2", "M"]), np.array(["x", "x"]))


def test_lovo_folds(arrays):
    folds = list(lovo_folds(arrays["trip_id"], level="family"))
    assert [f.held_out for f in folds] == sorted({trip_family(t) for t in arrays["trip_id"]})
    for f in folds:
        assert not np.any(f.train_mask & f.test_mask)
        assert f.test_mask.any() and f.train_mask.any()
        assert not {trip_family(t) for t in arrays["trip_id"][f.train_mask]} & {f.held_out}
    trip_folds = list(lovo_folds(arrays["trip_id"], level="trip", include_trips=["Vw2", "M", "S1"]))
    assert [f.held_out for f in trip_folds] == ["M", "S1", "Vw2"]


# ----------------------------------------------------------------------------- augmentation

@pytest.mark.parametrize("max_angle", [180.0, 30.0])
def test_rotation_matrices_are_proper(max_angle):
    r = random_rotation_matrices(200, np.random.default_rng(0), max_angle)
    np.testing.assert_allclose(r @ np.transpose(r, (0, 2, 1)), np.broadcast_to(np.eye(3), r.shape), atol=1e-10)
    np.testing.assert_allclose(np.linalg.det(r), 1.0, atol=1e-10)
    if max_angle < 180:
        angles = np.degrees(np.arccos(np.clip((np.trace(r, axis1=1, axis2=2) - 1) / 2, -1, 1)))
        assert angles.max() <= max_angle + 1e-6


def test_augmentation_properties(arrays):
    ds = from_arrays(arrays)
    ends = window_end_indices(ds, 20, 5)
    w = gather_windows(ds.imu, ends, 20)
    y = ds.target[ends].copy()
    out = augment_so3(w, np.random.default_rng(1))
    assert out.shape == w.shape and np.isfinite(out).all()
    np.testing.assert_array_equal(ds.target[ends], y)  # targets untouched
    np.testing.assert_array_equal(gather_windows(ds.imu, ends, 20), w)  # input not modified in place
    # norms preserved per sample and sensor (rotation), and the data actually changed
    np.testing.assert_allclose(np.linalg.norm(out[..., :3], axis=-1), np.linalg.norm(w[..., :3], axis=-1), rtol=1e-4)
    np.testing.assert_allclose(np.linalg.norm(out[..., 3:], axis=-1), np.linalg.norm(w[..., 3:], axis=-1), rtol=1e-4, atol=1e-6)
    assert not np.allclose(out, w)


def test_same_rotation_for_acc_and_gyr():
    rng = np.random.default_rng(3)
    v = rng.normal(size=(4, 10, 3)).astype(np.float64)
    w = np.concatenate([v, v], axis=-1)  # identical acc and gyr -> must stay identical
    out = augment_so3(w, np.random.default_rng(5))
    np.testing.assert_allclose(out[..., :3], out[..., 3:], atol=1e-12)
    # recover R per window from acc by least squares and check it maps gyr too, at every time step
    r = random_rotation_matrices(4, np.random.default_rng(9))
    acc, gyr = rng.normal(size=(4, 10, 3)), rng.normal(size=(4, 10, 3))
    rotated = rotate_windows(np.concatenate([acc, gyr], -1), r)
    np.testing.assert_allclose(rotated[..., :3], np.einsum("bij,btj->bti", r, acc), atol=1e-12)
    np.testing.assert_allclose(rotated[..., 3:], np.einsum("bij,btj->bti", r, gyr), atol=1e-12)


def test_augmentation_reproducible_and_probability(arrays):
    w = gather_windows(from_arrays(arrays).imu, np.arange(19, 119, 5), 20)
    a = augment_so3(w, np.random.default_rng(42))
    b = augment_so3(w, np.random.default_rng(42))
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(augment_so3(w, np.random.default_rng(0), probability=0.0), w)


# ----------------------------------------------------------------------------- yaw-only / gravity alignment (Milestone 3)

@pytest.mark.parametrize("max_angle", [180.0, 20.0])
def test_yaw_rotation_matrices_are_proper_and_preserve_vertical(max_angle):
    r = yaw_rotation_matrices(200, np.random.default_rng(0), max_angle)
    np.testing.assert_allclose(r @ np.transpose(r, (0, 2, 1)), np.broadcast_to(np.eye(3), r.shape), atol=1e-10)
    np.testing.assert_allclose(np.linalg.det(r), 1.0, atol=1e-10)
    np.testing.assert_allclose(r[:, 2, :], np.broadcast_to([0, 0, 1], (200, 3)), atol=1e-10)  # bottom row is [0,0,1]
    np.testing.assert_allclose(r[:, :, 2], np.broadcast_to([0, 0, 1], (200, 3)), atol=1e-10)  # R @ e_z == e_z (z axis fixed)


def test_augment_yaw_preserves_vertical_component(arrays):
    w = gather_windows(from_arrays(arrays).imu, np.arange(19, 119, 5), 20)
    out = augment_yaw(w, np.random.default_rng(1))
    assert out.shape == w.shape and np.isfinite(out).all()
    np.testing.assert_allclose(out[..., 2], w[..., 2], atol=1e-4)   # acc_z (vertical) unchanged
    np.testing.assert_allclose(out[..., 5], w[..., 5], atol=1e-4)   # gyr_z unchanged
    np.testing.assert_allclose(np.linalg.norm(out[..., :3], axis=-1), np.linalg.norm(w[..., :3], axis=-1), rtol=1e-4)
    assert not np.allclose(out[..., 0], w[..., 0])  # horizontal axes DO change


def test_yaw_reproducible_and_probability(arrays):
    w = gather_windows(from_arrays(arrays).imu, np.arange(19, 119, 5), 20)
    a = augment_yaw(w, np.random.default_rng(3))
    b = augment_yaw(w, np.random.default_rng(3))
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(augment_yaw(w, np.random.default_rng(0), probability=0.0), w)


def test_gravity_alignment_maps_mean_acc_to_plus_z():
    rng = np.random.default_rng(4)
    w = rng.normal(0, 0.3, size=(6, 15, 6)).astype(np.float32)
    w[..., 0:3] += rng.normal(size=(6, 1, 3)) * 3.0  # a random-but-fixed "gravity-like" direction per window
    w[..., 2] += 9.81
    aligned = align_to_gravity(w)
    g = aligned[..., 0:3].mean(axis=1)
    g_hat = g / np.linalg.norm(g, axis=1, keepdims=True)
    np.testing.assert_allclose(g_hat, np.broadcast_to([0.0, 0.0, 1.0], g_hat.shape), atol=1e-4)
    # a rotation must preserve vector norms (acc and gyro independently)
    np.testing.assert_allclose(np.linalg.norm(aligned[..., 0:3], axis=-1), np.linalg.norm(w[..., 0:3], axis=-1), rtol=1e-4)
    np.testing.assert_allclose(np.linalg.norm(aligned[..., 3:6], axis=-1), np.linalg.norm(w[..., 3:6], axis=-1), rtol=1e-4)


def test_gravity_alignment_degenerate_windows_keep_identity():
    zero = np.zeros((3, 10, 6), dtype=np.float32)
    np.testing.assert_array_equal(align_to_gravity(zero), zero)
    r = gravity_alignment_matrices(zero)
    np.testing.assert_allclose(r, np.broadcast_to(np.eye(3), r.shape))


def test_gravity_alignment_is_deterministic_no_randomness():
    rng = np.random.default_rng(5)
    w = rng.normal(size=(4, 12, 6)).astype(np.float32)
    w[..., 2] += 9.81
    np.testing.assert_array_equal(align_to_gravity(w), align_to_gravity(w))


@pytest.mark.parametrize("policy", AUGMENTATION_POLICIES)
def test_build_augmentation_and_representation_transform_pairing(policy, arrays):
    w = gather_windows(from_arrays(arrays).imu, np.arange(19, 119, 5), 20)
    so3_cfg = {"probability": 1.0, "max_angle_deg": 180.0}
    yaw_cfg = {"probability": 1.0, "max_angle_deg": 180.0}
    augment_fn = build_augmentation(policy, so3_cfg, yaw_cfg)
    repr_fn = representation_transform(policy)
    if policy == "none":
        assert augment_fn is None
    else:
        out = augment_fn(w, np.random.default_rng(0))
        assert out.shape == w.shape and np.isfinite(out).all()
    # the representation transform must be a no-op (up to a rotation, i.e. norm-preserving) always
    np.testing.assert_allclose(np.linalg.norm(repr_fn(w)[..., :3], axis=-1), np.linalg.norm(w[..., :3], axis=-1), rtol=1e-4)
    if policy == "gravity_yaw":
        assert not np.allclose(repr_fn(w), w)  # actually does something
    else:
        np.testing.assert_array_equal(repr_fn(w), w)  # identity for every other policy


def test_unknown_policy_rejected():
    with pytest.raises(ValueError):
        build_augmentation("bogus", {"probability": 1.0, "max_angle_deg": 180.0}, {"probability": 1.0, "max_angle_deg": 180.0})
    with pytest.raises(ValueError):
        representation_transform("bogus")


# ----------------------------------------------------------------------------- real dataset (only if present)

@pytest.mark.skipif(not REAL_NPZ.is_file(), reason="data/member1_imu_speed.npz not present")
def test_real_dataset_contract():
    with np.load(REAL_NPZ, allow_pickle=False) as z:
        keys = set(z.files)
        assert z["acc"].shape[1] == 3 and z["gyr"].shape[1] == 3
    assert {"acc", "gyr", "target_speed_mps", "session_id", "trip_id", "sample_idx", "t_session_s"} <= keys
    ds = load_npz(REAL_NPZ)
    assert ds.imu.shape[1] == 6 and np.isfinite(ds.imu).all()
    split = make_split(ds.trip_id, ds.session_id, SPLIT_RULES)
    assert split.trips["val"] == ["M"]
    assert all(t.startswith("S") for t in split.trips["test"])
    assert all(t.startswith("Vw") or t == "Vfa02" for t in split.trips["train"])
