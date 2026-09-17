from __future__ import annotations

import numpy as np
import pytest

from src.evaluation.robustness import (
    add_bias, add_drift, add_noise, evaluate_perturbations, make_perturbations, small_orientation_perturbation,
)

ROBUSTNESS_CFG = {
    "noise": {"acc_std_mps2": 0.5, "gyr_std_rads": 0.05},
    "vibration": {"acc_std_mps2": 1.5, "gyr_std_rads": 0.15},
    "bias": {"acc_bias_std_mps2": 0.3, "gyr_bias_std_rads": 0.02},
    "drift": {"acc_drift_mps2_per_s": 0.2, "gyr_drift_rads_per_s": 0.01},
    "orientation": {"max_angle_deg": 15.0},
}


@pytest.fixture
def windows():
    rng = np.random.default_rng(0)
    w = rng.normal(size=(6, 20, 6)).astype(np.float32)
    w[..., 2] += 9.81
    return w


def test_shapes_preserved(windows):
    rng = np.random.default_rng(1)
    for fn in (lambda w, r: add_noise(w, r, 0.5, 0.05), lambda w, r: add_bias(w, r, 0.3, 0.02),
              lambda w, r: add_drift(w, r, 0.2, 0.01, 10.0), lambda w, r: small_orientation_perturbation(w, r, 15.0)):
        out = fn(windows, rng)
        assert out.shape == windows.shape and out.dtype == windows.dtype and np.isfinite(out).all()


def test_add_noise_changes_every_sample(windows):
    out = add_noise(windows, np.random.default_rng(2), 0.5, 0.05)
    assert not np.allclose(out, windows)
    assert not np.allclose(out[:, 0], windows[:, 0]) and not np.allclose(out[:, -1], windows[:, -1])


def test_add_bias_is_constant_within_a_window(windows):
    out = add_bias(windows, np.random.default_rng(3), 0.3, 0.02)
    offset = out - windows
    np.testing.assert_allclose(offset[:, 0, :], offset[:, -1, :], rtol=1e-4, atol=1e-6)
    np.testing.assert_allclose(offset, np.broadcast_to(offset[:, :1, :], offset.shape), rtol=1e-4, atol=1e-6)
    assert not np.allclose(offset, 0)


def test_add_drift_starts_at_zero_and_grows(windows):
    out = add_drift(windows, np.random.default_rng(4), 0.2, 0.01, sample_rate_hz=10.0)
    offset = out - windows
    np.testing.assert_allclose(offset[:, 0, :], 0.0, atol=1e-6)
    assert np.all(np.linalg.norm(offset[:, -1, 0:3], axis=-1) > np.linalg.norm(offset[:, 5, 0:3], axis=-1))


def test_orientation_perturbation_is_a_rotation(windows):
    out = small_orientation_perturbation(windows, np.random.default_rng(5), 15.0)
    np.testing.assert_allclose(np.linalg.norm(out[..., 0:3], axis=-1), np.linalg.norm(windows[..., 0:3], axis=-1), atol=1e-4)
    np.testing.assert_allclose(np.linalg.norm(out[..., 3:6], axis=-1), np.linalg.norm(windows[..., 3:6], axis=-1), atol=1e-4)
    # a small rotation should stay close to the original acc direction (bounded by the max angle)
    cos_angle = np.sum(out[:, 0, 0:3] * windows[:, 0, 0:3], axis=-1) / (
        np.linalg.norm(out[:, 0, 0:3], axis=-1) * np.linalg.norm(windows[:, 0, 0:3], axis=-1))
    assert np.all(np.degrees(np.arccos(np.clip(cos_angle, -1, 1))) <= 15.0 + 1e-3)


def test_make_perturbations_and_evaluate(windows):
    perts = make_perturbations(ROBUSTNESS_CFG, sample_rate_hz=10.0)
    assert set(perts) == {"sensor_noise", "vibration", "sensor_bias", "sensor_drift", "orientation"}

    def predict_fn(ws):
        # a "sensitive" fake model whose mean depends on the mean acc magnitude, so perturbations
        # actually move the metrics (unlike a constant predictor, which would hide bugs)
        mean = np.linalg.norm(ws[..., 0:3], axis=-1).mean(axis=1)
        sigma = np.full(len(ws), 1.0)
        return mean, sigma

    y_true = predict_fn(windows)[0]  # "clean" predictions define ground truth -> clean MAE == 0
    report = evaluate_perturbations(predict_fn, windows, y_true, perts, seed=42)
    assert set(report) == {"clean", "sensor_noise", "vibration", "sensor_bias", "sensor_drift", "orientation"}
    assert report["clean"]["regression"]["mae_mps"] == pytest.approx(0.0, abs=1e-6)
    for name in perts:
        assert "regression" in report[name] and "uncertainty" in report[name]
        assert np.isfinite(report[name]["regression"]["mae_mps"])
    # vibration (larger noise std) should perturb the sensitive predictor more than plain sensor noise
    assert report["vibration"]["regression"]["mae_mps"] > report["sensor_noise"]["regression"]["mae_mps"]


def test_evaluate_perturbations_reproducible(windows):
    perts = make_perturbations(ROBUSTNESS_CFG, sample_rate_hz=10.0)

    def predict_fn(ws):
        return np.linalg.norm(ws[..., 0:3], axis=-1).mean(axis=1), np.full(len(ws), 1.0)

    y_true = np.full(len(windows), 9.81)
    r1 = evaluate_perturbations(predict_fn, windows, y_true, perts, seed=7)
    r2 = evaluate_perturbations(predict_fn, windows, y_true, perts, seed=7)
    for name in perts:
        assert r1[name]["regression"]["mae_mps"] == pytest.approx(r2[name]["regression"]["mae_mps"])
    r3 = evaluate_perturbations(predict_fn, windows, y_true, perts, seed=8)
    assert any(r1[name]["regression"]["mae_mps"] != pytest.approx(r3[name]["regression"]["mae_mps"]) for name in perts)
