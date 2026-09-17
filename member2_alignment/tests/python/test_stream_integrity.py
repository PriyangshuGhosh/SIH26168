from __future__ import annotations

import math

import numpy as np

from sih26168_alignment.frame_aligner import FrameAligner
from sih26168_alignment.types import CalibrationStatus


def test_100hz_synthetic_stream():
    al = FrameAligner()
    n = 400
    for i in range(n):
        f = al.process(0.01 * i, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
        assert f.status != CalibrationStatus.INVALID
        assert math.isfinite(f.ax_v) and math.isfinite(f.az_v)
        assert f.timestamp == 0.01 * i


def test_jitter_and_dropped():
    al = FrameAligner()
    t = 0.0
    for i in range(100):
        dt = 0.007 if i % 2 == 0 else 0.013
        t = 0.0 if i == 0 else t + dt
        f = al.process(t, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
        assert f.status != CalibrationStatus.INVALID
    dropped = al.process(t + 0.25, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
    assert dropped.status != CalibrationStatus.INVALID


def test_duplicate_and_ooo():
    al = FrameAligner()
    al.process(1.0, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
    dup = al.process(1.0, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
    assert dup.status == CalibrationStatus.INVALID
    ooo = al.process(0.5, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
    assert ooo.status == CalibrationStatus.INVALID
    nxt = al.process(1.01, 0.0, 0.0, 9.80665, 0.0, 0.0, 0.0)
    assert nxt.status != CalibrationStatus.INVALID


def test_deterministic_long_stream():
    def run():
        al = FrameAligner()
        return [
            al.process(0.01 * i, 0.04 * math.sin(0.02 * i), 0.0, 9.80665, 0.0, 0.0, 0.0)
            for i in range(1500)
        ]

    a = run()
    b = run()
    ax = np.array([f.ax_v for f in a])
    bx = np.array([f.ax_v for f in b])
    assert np.allclose(ax, bx)
    assert all(math.isfinite(f.q_pv[0]) for f in a)


def test_m1_window_channel_order():
    al = FrameAligner()
    window = np.zeros((6, 200), dtype=np.float32)
    for i in range(200):
        f = al.process(0.01 * i, 0.1, -0.2, 9.80665, 0.01, -0.02, 0.03)
        window[:, i] = [f.ax_v, f.ay_v, f.az_v, f.gx_v, f.gy_v, f.gz_v]
    assert np.isfinite(window).all()
    assert window[2, -1] > 8.0


def test_m1_100hz_window_layout():
    """Member 1 live ONNX is [T, 6] at 100 Hz; T=200 is 2 s with no decimation."""
    al = FrameAligner()
    win = []
    for i in range(200):
        f = al.process(0.01 * i, 0.15, 0.0, 9.80665, 0.0, 0.0, 0.0)
        assert f.status != CalibrationStatus.INVALID
        win.append([f.ax_v, f.ay_v, f.az_v, f.gx_v, f.gy_v, f.gz_v])
    arr = np.asarray(win, dtype=np.float32)
    assert arr.shape == (200, 6)
    assert np.isfinite(arr).all()
    assert arr[-1, 2] > 8.0
