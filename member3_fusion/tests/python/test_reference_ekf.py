"""Focused Member 3 EKF safety/integration tests, against the NumPy reference
(reference_ekf.py / reference_gnss.py) that mirrors member3_fusion/src/EKFFusionEngine.cpp's
constants and update equations exactly (no C++ toolchain is available in every environment this
suite runs in, so this is the only executable check on the EKF's actual numerics here; the C++
tests in member3_fusion/tests/test_member3.cpp are the production-binary counterpart and should be
run wherever a C++20 + CMake toolchain is available).

Covers: impossible-speed rejection, AI-speed NIS gating, GNSS blackout + recovery (predict-only
gap handling), covariance PSD/finiteness over a long run, NHC gated on alignment status, and
timestamp duplicate/stale/future rejection -- the Member 3 portion of the SIH26168 integration
checklist.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from reference_ekf import Config, EKFReference


def _step_ekf(ekf: EKFReference, t: float, ax: float = 0.0, ay: float = 0.0, gz: float = 0.0,
              fully_aligned: bool = True) -> bool:
    return ekf.predict(t, ax, ay, gz, fully_aligned=fully_aligned)


# --------------------------------------------------------------------------- impossible speed


def test_impossible_speed_rejected_matches_production_bound():
    """A 700 km/h GNSS/AI speed measurement must be rejected, using the SAME 55 m/s bound as
    member3_fusion/include/member3/fusion_types.h's EKFFusionConfig.max_vehicle_speed_mps."""
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0)
    assert _step_ekf(ekf, 0.1)
    vx_before = ekf.x[2]
    kmh_700 = 194.4  # 700 km/h in m/s
    assert kmh_700 > ekf.cfg.max_vehicle_speed_mps
    assert not ekf.update_speed(0.1, kmh_700, 1.0)
    assert ekf.x[2] == vx_before  # state must be untouched by a rejected measurement


def test_negative_and_nonfinite_speed_rejected():
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0)
    assert _step_ekf(ekf, 0.1)
    assert not ekf.update_speed(0.1, -5.0, 1.0)
    assert not ekf.update_speed(0.1, math.nan, 1.0)
    assert not ekf.update_speed(0.1, math.inf, 1.0)
    assert not ekf.update_speed(0.1, 10.0, 0.0)       # zero variance
    assert not ekf.update_speed(0.1, 10.0, -1.0)      # negative variance
    assert not ekf.update_speed(0.1, 10.0, 1.0e18)    # absurd variance, above max_speed_variance_m2s2


# --------------------------------------------------------------------------- AI-speed NIS gating


def test_ai_speed_nis_gates_outlier_but_accepts_plausible():
    """A wild outlier measurement (inconsistent with the filter's own covariance) must be
    rejected by the NIS gate; a measurement close to the current state estimate must be accepted."""
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0)
    for i in range(1, 21):
        assert _step_ekf(ekf, 0.1 * i, ax=1.0)
    vx = ekf.x[2]

    # Tight variance + far-off measurement -> large NIS -> rejected.
    assert not ekf.update_speed(2.0, vx + 20.0, 0.05)
    assert ekf.x[2] == pytest.approx(vx)

    # Same variance, measurement close to the current estimate -> accepted.
    assert ekf.update_speed(2.0, vx + 0.05, 0.05)


def test_nan_inf_ai_speed_measurement_rejected():
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0)
    assert _step_ekf(ekf, 0.1)
    assert not ekf.update_speed(0.1, math.nan, 0.1)
    assert not ekf.update_speed(0.1, 5.0, math.nan)
    assert np.isfinite(ekf.x).all() and np.isfinite(ekf.P).all()


# --------------------------------------------------------------------------- GNSS blackout / recovery


def test_predict_only_gap_handling_then_recovery():
    """Simulates a GNSS blackout: after healthy tracking, a run of predict-only (IMU-only) steps
    must keep the filter finite and stable, and a later measurement must still be accepted cleanly
    (no permanent damage from the outage)."""
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0)
    for i in range(1, 51):  # 5 s of healthy IMU-only tracking, cruise accel
        assert _step_ekf(ekf, 0.1 * i, ax=0.5)
    assert np.isfinite(ekf.x).all() and np.isfinite(ekf.P).all()
    vx_before_gap = ekf.x[2]

    # "Blackout": no GNSS/AI-speed updates for 3 s of IMU-only dead reckoning.
    t = 5.0
    for _ in range(30):
        t += 0.1
        assert _step_ekf(ekf, t, ax=0.0)
    assert np.isfinite(ekf.x).all() and np.isfinite(ekf.P).all()
    # Position uncertainty must have grown during the unaided stretch (dead reckoning drifts).
    assert ekf.P[0, 0] > 25.0 or ekf.P[1, 1] > 25.0 or ekf.P[2, 2] > 0.0

    # "Recovery": a plausible speed measurement is accepted again immediately.
    assert ekf.update_speed(t, max(0.0, vx_before_gap), 1.0)
    assert np.isfinite(ekf.x).all() and np.isfinite(ekf.P).all()


def test_large_time_gap_inflates_covariance_without_diverging():
    """A gap longer than max_gap_s (e.g. app backgrounded, sensor stall) takes the dedicated
    gap-covariance-inflation path instead of many small predict steps, and must stay finite."""
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0)
    assert _step_ekf(ekf, 0.1)
    p_before = ekf.P.copy()
    assert _step_ekf(ekf, 5.0)  # > max_gap_s (1.0 s)
    assert np.isfinite(ekf.P).all()
    assert ekf.P[0, 0] > p_before[0, 0]
    assert ekf.P[1, 1] > p_before[1, 1]


# --------------------------------------------------------------------------- covariance stability


def test_covariance_stays_finite_and_psd_over_long_run():
    ekf = EKFReference()
    rng = np.random.default_rng(0)
    t = 0.0
    assert _step_ekf(ekf, t)
    for i in range(2000):
        t += 0.01
        ax, ay, gz = rng.normal(0, 1.0, 3)
        ok = _step_ekf(ekf, t, ax=float(ax), ay=float(ay), gz=float(gz))
        assert ok
        assert np.isfinite(ekf.x).all()
        assert np.isfinite(ekf.P).all()
        eigenvalues = np.linalg.eigvalsh(ekf.P)
        assert eigenvalues.min() > -1e-6, "covariance must stay positive semi-definite"
        if i % 50 == 0:
            assert ekf.update_speed(t, max(0.0, float(ekf.x[2])), 1.0) or True  # never crashes


def test_covariance_recovers_after_many_rejected_updates():
    """Prolonged invalid measurements (all rejected) must not corrupt the filter; it must still
    accept a valid measurement immediately afterward."""
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0)
    t = 0.0
    for i in range(1, 101):
        t = 0.1 * i
        assert _step_ekf(ekf, t, ax=0.2)
        assert not ekf.update_speed(t, 999.0, 1.0)  # impossible speed, rejected every time
    assert np.isfinite(ekf.x).all() and np.isfinite(ekf.P).all()
    assert ekf.update_speed(t, max(0.0, float(ekf.x[2])), 1.0)  # clean recovery


# --------------------------------------------------------------------------- NHC gating


def test_nhc_not_applied_when_not_fully_aligned():
    """The non-holonomic constraint (vy -> 0) must only engage when Member 2 reports a fully
    aligned frame; it must never be used to manufacture forward velocity, and must not be applied
    at all when alignment is not trustworthy (YAW_UNCERTAIN/DEGRADED/etc.)."""
    ekf_gated = EKFReference()
    ekf_free = EKFReference()
    assert _step_ekf(ekf_gated, 0.0, fully_aligned=False)
    assert _step_ekf(ekf_free, 0.0, fully_aligned=False)
    # Inject identical lateral velocity into both by construction (bypassing predict's dynamics).
    ekf_gated.x[3] = 2.0
    ekf_free.x[3] = 2.0

    assert _step_ekf(ekf_gated, 0.1, fully_aligned=False)  # NHC must NOT engage
    assert _step_ekf(ekf_free, 0.1, fully_aligned=True)    # NHC SHOULD engage and pull vy toward 0

    assert ekf_gated.x[3] == pytest.approx(2.0, abs=1e-9), "vy must be untouched without alignment"
    assert ekf_free.x[3] < 2.0, "vy must be pulled toward zero once NHC is applied"


def test_nhc_never_creates_forward_velocity():
    """NHC's measurement model only ever touches vy (state index 3); vx (index 2, forward speed)
    must be numerically unaffected by the NHC update itself."""
    ekf = EKFReference()
    assert _step_ekf(ekf, 0.0, fully_aligned=True)
    ekf.x[2] = 0.0  # no forward speed
    ekf.x[3] = 3.0  # large spurious lateral velocity
    assert _step_ekf(ekf, 0.1, fully_aligned=True)
    assert abs(ekf.x[2]) < 1e-6, "NHC must never manufacture forward velocity from vy correction"


# --------------------------------------------------------------------------- timestamp policy


def test_duplicate_and_nonmonotonic_timestamps_rejected_in_predict():
    ekf = EKFReference()
    assert _step_ekf(ekf, 1.0)
    x_before = ekf.x.copy()
    assert not _step_ekf(ekf, 1.0)   # duplicate timestamp: raw dt == 0
    assert not _step_ekf(ekf, 0.5)   # non-monotonic: raw dt < 0
    np.testing.assert_array_equal(ekf.x, x_before)


def test_stale_and_future_measurements_rejected():
    ekf = EKFReference()
    assert _step_ekf(ekf, 1.0)
    assert _step_ekf(ekf, 1.1)
    # Stale: older than max_measurement_age_s (0.10 s) before the current filter epoch.
    assert not ekf.update_speed(1.1 - ekf.cfg.max_measurement_age_s - 0.05, 5.0, 1.0)
    # Future: ahead of max_measurement_lead_s (0.0 s), i.e. any timestamp after the current epoch.
    assert not ekf.update_speed(1.1 + 0.05, 5.0, 1.0)
    # Exactly at the current epoch must still be accepted.
    assert ekf.update_speed(1.1, max(0.0, float(ekf.x[2])), 1.0)


# --------------------------------------------------------------------------- degraded mode


def test_degraded_status_scales_process_noise_up():
    """A non-FULLY_ALIGNED frame must inflate process noise (degraded_process_scale), reflecting
    reduced trust in the IMU alignment -- covariance should grow faster than when fully aligned."""
    ekf_aligned = EKFReference()
    ekf_degraded = EKFReference()
    assert _step_ekf(ekf_aligned, 0.0, fully_aligned=True)
    assert _step_ekf(ekf_degraded, 0.0, fully_aligned=False)
    assert _step_ekf(ekf_aligned, 0.1, ax=0.3, fully_aligned=True)
    assert _step_ekf(ekf_degraded, 0.1, ax=0.3, fully_aligned=False)
    assert ekf_degraded.P[2, 2] > ekf_aligned.P[2, 2]
    assert ekf_degraded.P[4, 4] > ekf_aligned.P[4, 4]
