from __future__ import annotations

import numpy as np
import pytest

from conftest import SPLIT_RULES
from src.data.dataset import from_arrays
from src.data.splits import make_split
from src.data.windowing import gather_windows, window_end_indices
from src.evaluation.metrics import regression_metrics
from src.models.baselines import (
    FEATURE_NAMES, ConstantMeanBaseline, PhysicsIntegrationBaseline, RidgeFeatureBaseline, window_features,
)


@pytest.fixture
def split_data(arrays):
    ds = from_arrays(arrays)
    split = make_split(ds.trip_id, ds.session_id, SPLIT_RULES)
    subsets = {s: ds.subset(split.masks[s]) for s in ("train", "val", "test")}
    ends = {"train": window_end_indices(subsets["train"], 20, 5),
            "val": window_end_indices(subsets["val"], 20, 1),
            "test": window_end_indices(subsets["test"], 20, 1)}
    return subsets, ends


def test_constant_mean(split_data):
    subsets, ends = split_data
    y = subsets["train"].target[ends["train"]]
    model = ConstantMeanBaseline().fit(y)
    p = model.predict(len(ends["test"]))
    assert p.shape == (len(ends["test"]),) and np.allclose(p, y.mean())


def test_window_features_shape_and_rejects_bad_input():
    w = np.random.default_rng(0).normal(size=(7, 40, 6)).astype(np.float32)
    f = window_features(w)
    assert f.shape == (7, len(FEATURE_NAMES)) == (7, 48) and np.isfinite(f).all()
    with pytest.raises(ValueError):
        window_features(w[..., :5])  # anything but exactly 6 IMU channels is refused


def test_ridge_end_to_end(split_data):
    subsets, ends = split_data
    tr = subsets["train"]
    xw = gather_windows(tr.imu, ends["train"], 20)
    model = RidgeFeatureBaseline(alpha=1.0).fit(xw, tr.target[ends["train"]])
    for s in ("val", "test"):
        p = model.predict_indexed(subsets[s].imu, ends[s], 20, chunk_size=17)  # odd chunk size exercises chunking
        full = model.predict(gather_windows(subsets[s].imu, ends[s], 20))
        np.testing.assert_allclose(p, full)
        assert p.shape == (len(ends[s]),) and (p >= 0).all()
        assert np.isfinite(list(regression_metrics(subsets[s].target[ends[s]], p).values())).all()


def test_physics_baseline_end_to_end_and_causal(split_data, arrays):
    subsets, ends = split_data
    model = PhysicsIntegrationBaseline().fit(subsets["train"], ends["train"], [0.05, 0.2], [30.0, float("inf")])
    assert len(model.grid_results_) == 4
    rows = model.predict_rows(subsets["test"])
    assert rows.shape == (len(subsets["test"]),) and np.isfinite(rows).all() and (rows >= 0).all()

    # causality: perturbing rows after e must not change the estimate at rows <= e
    ds = from_arrays(arrays)
    base = model.predict_rows(ds)
    e = 60
    changed = dict(arrays, acc=arrays["acc"].copy())
    changed["acc"][e + 1:] += 5.0
    np.testing.assert_allclose(model.predict_rows(from_arrays(changed))[:e + 1], base[:e + 1])


def test_physics_integrates_constant_acceleration():
    n = 50
    arrays = {
        "acc": np.tile(np.array([[0.0, 0.0, 9.81]], dtype=np.float32), (n, 1)),
        "gyr": np.zeros((n, 3), dtype=np.float32) + 0.5,  # rotating -> never flagged stationary
        "target_speed_mps": np.zeros(n, dtype=np.float32), "t_session_s": np.arange(n, dtype=np.float32) * 0.1,
        "session_id": np.full(n, "X__s00"), "trip_id": np.full(n, "X"), "sample_idx": np.arange(n),
    }
    model = PhysicsIntegrationBaseline(gravity_tau_s=1e6, leak_tau_s=float("inf"), zupt_gyr_std=-1.0)
    arrays["acc"][:, 0] = 1.0  # constant 1 m/s^2 horizontal after an initial gravity estimate
    arrays["acc"][0, 0] = 0.0
    v = model.predict_rows(from_arrays(arrays))
    # speed grows roughly linearly at ~1 m/s^2 (gravity EMA barely adapts with a huge tau)
    assert v[-1] == pytest.approx((n - 1) * 0.1, rel=0.05)
