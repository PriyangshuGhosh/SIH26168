"""Tests for the production Member 2 -> Member 1 interface: consuming a genuine 100 Hz
``AlignedIMUFrame`` stream, causal buffering/gating on status, decimation to the model's native
10 Hz resolution, and structural compatibility with Member 2's actual Python reference dataclass.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from src.inference.member2_interface import (
    DECIMATION_FACTOR,
    FULLY_ALIGNED,
    MODEL_NATIVE_WINDOW,
    PRODUCTION_RAW_WINDOW,
    PRODUCTION_SAMPLE_RATE_HZ,
    ProductionWindowBuffer,
    decimate,
    frame_to_channels,
    is_fully_aligned,
    production_window_to_model_input,
)
from src.data.windowing import SAMPLE_RATE_HZ as MODEL_SAMPLE_RATE_HZ


@dataclass
class FakeFrame:
    """Minimal stand-in for ``sih26168_alignment.types.AlignedIMUFrame`` with the same field names."""

    timestamp: float
    ax_v: float
    ay_v: float
    az_v: float
    gx_v: float
    gy_v: float
    gz_v: float
    status: int = FULLY_ALIGNED
    confidence: float = 0.9  # deliberately not a real CalibrationConfidence; must never reach the model


def make_frame(i: int, status: int = FULLY_ALIGNED, hz: float = PRODUCTION_SAMPLE_RATE_HZ) -> FakeFrame:
    return FakeFrame(timestamp=i / hz, ax_v=float(i), ay_v=float(i) + 100.0, az_v=9.81,
                      gx_v=0.01 * i, gy_v=-0.01 * i, gz_v=0.0, status=status)


# --------------------------------------------------------------------------------------- constants


def test_production_window_is_2s_at_100hz():
    assert PRODUCTION_SAMPLE_RATE_HZ == 100.0
    assert PRODUCTION_RAW_WINDOW == 200


def test_decimation_maps_100hz_window_to_model_native_10hz_window():
    assert DECIMATION_FACTOR == round(PRODUCTION_SAMPLE_RATE_HZ / MODEL_SAMPLE_RATE_HZ)
    assert MODEL_NATIVE_WINDOW == PRODUCTION_RAW_WINDOW // DECIMATION_FACTOR == 20


# --------------------------------------------------------------------------------- channel/leakage


def test_frame_to_channels_reads_only_the_six_kinematic_fields():
    """Only ax_v..gz_v may reach the model -- never timestamp, status or confidence (mirrors the
    leakage discipline src.data.dataset.build_model_input enforces for the training data)."""
    f = make_frame(7)
    ch = frame_to_channels(f)
    assert ch.shape == (6,)
    assert ch.dtype == np.float32
    np.testing.assert_allclose(ch, [f.ax_v, f.ay_v, f.az_v, f.gx_v, f.gy_v, f.gz_v])
    # A frame whose timestamp/confidence are huge outliers must not perturb the channels.
    f2 = FakeFrame(timestamp=1e9, ax_v=1.0, ay_v=2.0, az_v=3.0, gx_v=4.0, gy_v=5.0, gz_v=6.0,
                   status=FULLY_ALIGNED, confidence=1e9)
    np.testing.assert_allclose(frame_to_channels(f2), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])


def test_is_fully_aligned_gates_on_status_value():
    assert is_fully_aligned(make_frame(0, status=FULLY_ALIGNED))
    for other in (0, 1, 2, 3, 5, 6, 7):
        assert not is_fully_aligned(make_frame(0, status=other))


# -------------------------------------------------------------------------------------- decimation


def test_decimate_keeps_the_most_recent_sample_of_each_block_causally():
    raw = np.arange(PRODUCTION_RAW_WINDOW * 6, dtype=np.float32).reshape(PRODUCTION_RAW_WINDOW, 6)
    out = decimate(raw)
    assert out.shape == (MODEL_NATIVE_WINDOW, 6)
    # The kept row indices are 9, 19, 29, ... (last of each 10-sample block) -- never a future row.
    expected_rows = raw[DECIMATION_FACTOR - 1::DECIMATION_FACTOR]
    np.testing.assert_array_equal(out, expected_rows)


def test_decimate_rejects_non_multiple_length():
    with pytest.raises(ValueError):
        decimate(np.zeros((205, 6), dtype=np.float32))


def test_decimate_rejects_wrong_channel_count():
    with pytest.raises(ValueError):
        decimate(np.zeros((200, 5), dtype=np.float32))


def test_production_window_to_model_input_requires_exact_raw_length():
    with pytest.raises(ValueError):
        production_window_to_model_input(np.zeros((199, 6), dtype=np.float32))
    out = production_window_to_model_input(np.zeros((PRODUCTION_RAW_WINDOW, 6), dtype=np.float32))
    assert out.shape == (MODEL_NATIVE_WINDOW, 6)
    assert out.dtype == np.float32


# ------------------------------------------------------------------------------------ ring buffer
#
# stride=1 is used below wherever the test is about fill/reset mechanics (so "full" and "emits"
# coincide exactly); the default stride (== DECIMATION_FACTOR) is exercised separately.


def test_buffer_emits_only_once_full_and_causal_no_future_samples():
    buf = ProductionWindowBuffer(stride=1)
    for i in range(PRODUCTION_RAW_WINDOW - 1):
        assert buf.push(make_frame(i)) is None
    emitted = buf.push(make_frame(PRODUCTION_RAW_WINDOW - 1))
    assert emitted is not None
    raw, ts = emitted
    assert raw.shape == (PRODUCTION_RAW_WINDOW, 6)
    # timestamp is the most recent (last) frame's own timestamp -- the prediction point, matching
    # the training convention that a window is labelled at its last sample.
    assert ts == pytest.approx((PRODUCTION_RAW_WINDOW - 1) / PRODUCTION_SAMPLE_RATE_HZ)
    # Every row's implied index is <= the emission frame's index (no lookahead).
    np.testing.assert_allclose(raw[:, 0], np.arange(PRODUCTION_RAW_WINDOW, dtype=np.float32))


def test_buffer_emits_at_stride_cadence_after_first_full_window():
    """With the default stride (== DECIMATION_FACTOR), the first emission lands ``stride - 1``
    frames after the buffer first fills, then one emission every ``stride`` frames after that."""
    buf = ProductionWindowBuffer(stride=DECIMATION_FACTOR)
    frames = [make_frame(i) for i in range(PRODUCTION_RAW_WINDOW + 3 * DECIMATION_FACTOR)]
    emission_indices = [i for i, f in enumerate(frames) if buf.push(f) is not None]
    first_full_index = PRODUCTION_RAW_WINDOW - 1
    assert emission_indices[0] == first_full_index + (DECIMATION_FACTOR - 1)
    assert all(b - a == DECIMATION_FACTOR for a, b in zip(emission_indices, emission_indices[1:]))


def test_buffer_resets_on_non_fully_aligned_status():
    buf = ProductionWindowBuffer(stride=1)
    for i in range(PRODUCTION_RAW_WINDOW - 1):
        buf.push(make_frame(i))
    # One YAW_UNCERTAIN frame right before completion must discard the accumulated history.
    assert buf.push(make_frame(PRODUCTION_RAW_WINDOW - 1, status=3)) is None
    for i in range(PRODUCTION_RAW_WINDOW - 1):
        assert buf.push(make_frame(PRODUCTION_RAW_WINDOW + i)) is None
    assert buf.push(make_frame(2 * PRODUCTION_RAW_WINDOW - 1)) is not None


def test_buffer_reset_method_clears_history():
    buf = ProductionWindowBuffer(stride=1)
    for i in range(PRODUCTION_RAW_WINDOW - 5):
        buf.push(make_frame(i))
    buf.reset()
    for i in range(PRODUCTION_RAW_WINDOW - 1):
        assert buf.push(make_frame(i)) is None
    assert buf.push(make_frame(PRODUCTION_RAW_WINDOW - 1)) is not None


def test_buffer_rejects_raw_window_not_multiple_of_decimation_factor():
    with pytest.raises(ValueError):
        ProductionWindowBuffer(raw_window=205)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_buffer_resets_on_non_finite_channel_even_if_status_claims_fully_aligned(bad_value):
    """Defense in depth: a FULLY_ALIGNED frame should never carry NaN/Inf per Member 2's own status
    machine (that's what INVALID is for), but the buffer must not silently poison a window if one
    slips through -- matching src.data.windowing's finite-value invariant on the training data."""
    buf = ProductionWindowBuffer(stride=1)
    for i in range(PRODUCTION_RAW_WINDOW - 1):
        buf.push(make_frame(i))
    bad = make_frame(PRODUCTION_RAW_WINDOW - 1)
    bad.ax_v = bad_value
    assert buf.push(bad) is None
    for i in range(PRODUCTION_RAW_WINDOW - 1):
        assert buf.push(make_frame(PRODUCTION_RAW_WINDOW + i)) is None
    assert buf.push(make_frame(2 * PRODUCTION_RAW_WINDOW - 1)) is not None


# -------------------------------------------------------------------------- structural compatibility


def test_structurally_compatible_with_real_member2_aligned_imu_frame():
    """Prove this module works with Member 2's actual ``AlignedIMUFrame`` dataclass, not just the
    local ``FakeFrame`` stand-in -- imported directly from ``member2_alignment/python``."""
    member2_python = Path(__file__).resolve().parents[2] / "member2_alignment" / "python"
    if not member2_python.is_dir():
        pytest.skip("member2_alignment/python not present in this checkout")
    sys.path.insert(0, str(member2_python))
    try:
        from sih26168_alignment.types import AlignedIMUFrame, CalibrationStatus
    except ImportError:
        pytest.skip("sih26168_alignment package (Member 2 Python reference) is not importable")
    finally:
        sys.path.remove(str(member2_python))

    frame = AlignedIMUFrame(timestamp=1.23, ax_v=1.0, ay_v=2.0, az_v=3.0, gx_v=4.0, gy_v=5.0, gz_v=6.0,
                             status=CalibrationStatus.FULLY_ALIGNED)
    assert is_fully_aligned(frame)
    np.testing.assert_allclose(frame_to_channels(frame), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    degraded = AlignedIMUFrame(timestamp=1.24, ax_v=1.0, ay_v=2.0, az_v=3.0, gx_v=4.0, gy_v=5.0, gz_v=6.0,
                                status=CalibrationStatus.YAW_UNCERTAIN)
    assert not is_fully_aligned(degraded)
