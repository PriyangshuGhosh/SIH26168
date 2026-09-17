from __future__ import annotations

import numpy as np
import pytest

from src.evaluation.metrics import (
    calibration_report, coverage, full_report, mae, metrics_by_group, metrics_by_speed_bin, metrics_stationary_moving,
    nll_gaussian, r2, regression_metrics, rmse, sharpness,
)


def test_known_values():
    y = np.array([0.0, 1.0, 2.0, 3.0])
    p = np.array([0.0, 2.0, 2.0, 1.0])
    assert mae(y, p) == pytest.approx(0.75)
    assert rmse(y, p) == pytest.approx(np.sqrt(5 / 4))
    assert r2(y, p) == pytest.approx(1 - 5 / 5)
    assert r2(y, y) == pytest.approx(1.0)
    assert r2(y, np.full(4, y.mean())) == pytest.approx(0.0)
    m = regression_metrics(y, p)
    assert m["mae_kmh"] == pytest.approx(0.75 * 3.6) and m["n"] == 4


def test_matches_sklearn():
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    rng = np.random.default_rng(0)
    y, p = rng.uniform(0, 30, 500), rng.uniform(0, 30, 500)
    assert mae(y, p) == pytest.approx(mean_absolute_error(y, p))
    assert rmse(y, p) == pytest.approx(np.sqrt(mean_squared_error(y, p)))
    assert r2(y, p) == pytest.approx(r2_score(y, p))


def test_input_validation():
    with pytest.raises(ValueError):
        mae(np.zeros(3), np.zeros(4))
    with pytest.raises(ValueError):
        mae(np.array([np.nan]), np.array([0.0]))
    assert np.isnan(r2(np.ones(3), np.zeros(3)))


def test_breakdowns():
    y = np.array([0.0, 0.2, 5.0, 12.0, 25.0, 31.0])
    p = y + np.array([1.0, 1.0, -1.0, 2.0, 0.0, -3.0])
    g = np.array(["a", "a", "b", "b", "c", "c"])
    by_group = metrics_by_group(y, p, g)
    assert by_group["a"]["mae_mps"] == pytest.approx(1.0) and by_group["c"]["mae_mps"] == pytest.approx(1.5)
    sm = metrics_stationary_moving(y, p, 0.5)
    assert sm["stationary"]["n"] == 2 and sm["moving"]["n"] == 4
    bins = metrics_by_speed_bin(y, p, [0.0, 0.5, 10.0, 20.0, float("inf")])
    assert [b["n"] for b in bins.values()] == [2, 1, 1, 2]
    report = full_report(y, p, {"trip": g}, 0.5, [0.0, 10.0, float("inf")])
    assert set(report) == {"overall", "by_trip", "stationary_vs_moving", "by_speed_bin_mps"}


# --------------------------------------------------------------------------------- calibration

def test_nll_gaussian_known_value():
    y = np.array([0.0, 2.0])
    mean = np.array([0.0, 0.0])
    sigma = np.array([1.0, 1.0])
    # 0.5*(log(2*pi*1) + 0) and 0.5*(log(2*pi) + 4)
    expected = (0.5 * (np.log(2 * np.pi) + 0.0) + 0.5 * (np.log(2 * np.pi) + 4.0)) / 2
    assert nll_gaussian(y, mean, sigma) == pytest.approx(expected)


def test_coverage_known_values():
    y = np.array([0.0, 1.0, 3.0, -3.0])
    mean = np.zeros(4)
    sigma = np.ones(4)
    assert coverage(y, mean, sigma, z=1.0) == pytest.approx(0.5)   # |0|,|1| within 1sigma; |3|,|-3| not
    assert coverage(y, mean, sigma, z=3.0) == pytest.approx(1.0)


def test_sharpness():
    s = np.array([1.0, 2.0, 3.0])
    r = sharpness(s)
    assert r == {"mean_sigma_mps": pytest.approx(2.0), "median_sigma_mps": pytest.approx(2.0),
                "min_sigma_mps": pytest.approx(1.0), "max_sigma_mps": pytest.approx(3.0)}


def test_calibration_report_well_calibrated_vs_over_and_underconfident():
    rng = np.random.default_rng(0)
    n = 20000
    mean = rng.uniform(0, 30, n)
    true_sigma = rng.uniform(0.5, 3.0, n)
    y = mean + rng.normal(0, 1, n) * true_sigma

    good = calibration_report(y, mean, true_sigma)
    assert good["levels"]["0.68"]["observed_coverage"] == pytest.approx(0.68, abs=0.02)
    assert good["levels"]["0.95"]["observed_coverage"] == pytest.approx(0.95, abs=0.02)
    assert good["error_sigma_correlation"] > 0.2  # higher true sigma -> higher observed error

    overconfident = calibration_report(y, mean, true_sigma * 0.3)  # sigma too small
    assert overconfident["levels"]["0.68"]["observed_coverage"] < 0.68 - 0.05

    underconfident = calibration_report(y, mean, true_sigma * 3.0)  # sigma too large
    assert underconfident["levels"]["0.68"]["observed_coverage"] > 0.68 + 0.05
    assert underconfident["mean_sigma_mps"] > good["mean_sigma_mps"]  # less sharp


def test_calibration_rejects_bad_sigma():
    y, mean = np.zeros(3), np.zeros(3)
    with pytest.raises(ValueError):
        nll_gaussian(y, mean, np.array([1.0, -1.0, 1.0]))
    with pytest.raises(ValueError):
        nll_gaussian(y, mean, np.array([1.0, np.inf, 1.0]))
    with pytest.raises(ValueError):
        calibration_report(y, mean, np.ones(2))  # shape mismatch
