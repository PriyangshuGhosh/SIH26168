from __future__ import annotations

import math

from sih26168_v2x_demo.engine import DemoEngine
from sih26168_v2x_demo.scenarios import SCENARIO_PRESETS, recording_spec, caption_at


def test_recording_seed_is_fixed():
    spec = recording_spec()
    assert spec.seed == 7
    assert spec.n_remotes == 3
    assert spec.gnss_outage_s == 10.0
    assert spec.inject_bad_at_s == 20.0
    a = DemoEngine(spec)
    b = DemoEngine(recording_spec())
    fa = a.run_steps(40)
    fb = b.run_steps(40)
    assert abs(fa.baseline_err_m - fb.baseline_err_m) < 1e-12
    assert abs(fa.v2x_err_m - fb.v2x_err_m) < 1e-12
    assert fa.received == fb.received


def test_reset_restores_time_and_counters():
    e = DemoEngine(SCENARIO_PRESETS["normal"])
    e.run_steps(15)
    assert e.t > 0
    e.reset(SCENARIO_PRESETS["normal"])
    s = e.snapshot()
    assert e.t == 0.0
    assert s.received == 0
    assert s.accepted == 0
    assert abs(s.baseline_err_m) < 1e-9
    assert abs(s.v2x_err_m) < 1e-9


def test_gnss_outage_event():
    e = DemoEngine(SCENARIO_PRESETS["outage_3"])
    e.run_steps(99)
    assert e.t < 10.0
    assert e.gnss_available()
    e.run_steps(5)
    assert e.t >= 10.0
    assert not e.gnss_available()
    e.trigger_gnss_outage()
    e.reset(SCENARIO_PRESETS["normal"])
    assert e.gnss_available()
    e.trigger_gnss_outage()
    assert not e.gnss_available()


def test_bad_vehicle_event_and_gate():
    e = DemoEngine(SCENARIO_PRESETS["outage_bad"])
    e.run_steps(int(20.0 / e.spec.dt_s) + 2)
    assert e.bad_injected
    assert e.t >= 20.0
    # After the jump, fused NIS should not be a silent accept of a 55 m east bias.
    # Either REJECT or a clearly large NIS on a per-track link.
    gates = {lk.gate for lk in e.links}
    assert e.rejected_gate >= 1 or "REJECT" in gates or e.fused_nis > 5.991


def test_message_counters_and_metric_consistency():
    e = DemoEngine(SCENARIO_PRESETS["outage_3"])
    f = e.run_steps(30)
    assert f.received > 0
    assert f.n_remotes == 3
    assert f.validated >= 1
    n_true = 16.0 * (e.t - e.spec.dt_s)
    # snapshot is taken before t increment, last frame.t matches last update epoch
    last = e.error_history[-1]
    assert abs(last[1] - f.baseline_err_m) < 1e-9
    assert abs(last[2] - f.v2x_err_m) < 1e-9
    recon = math.hypot(e.baseline.n - n_true, e.baseline.e - 0.0)
    assert abs(recon - f.baseline_err_m) < 1e-6


def test_zero_remotes_fallback():
    e = DemoEngine(SCENARIO_PRESETS["gnss_outage"])
    f = e.run_steps(120)
    assert f.n_remotes == 0
    assert f.fused_decision in ("UNAVAILABLE", "REJECT")
    # No V2X measurement → filters share IMU/AI/GNSS and stay close while GNSS is on,
    # then both drift similarly after outage.
    assert f.received == 0


def test_remote_count_switch():
    e = DemoEngine(SCENARIO_PRESETS["outage_1"])
    e.set_remote_count(10)
    assert e.spec.n_remotes == 10
    f = e.run_steps(5)
    assert f.n_remotes == 10


def test_captions_follow_recording_timeline():
    assert "normally" in caption_at(1.0).lower()
    assert "GNSS" in caption_at(10.0)
    assert "bad" in caption_at(20.0).lower()
    assert "NIS" in caption_at(21.0)


def test_svg_screenshot_is_simulation_labelled(tmp_path):
    from sih26168_v2x_demo.svg_export import write_svg

    e = DemoEngine(recording_spec())
    e.run_steps(int(12.0 / e.spec.dt_s))
    path = tmp_path / "frame.svg"
    write_svg(path, e)
    text = path.read_text(encoding="utf-8")
    assert "SIMULATION" in text
    assert "V2X RADIO: SIMULATED" in text
    assert "GNSS SIGNAL LOST" in text
    assert "real c-v2x" not in text.lower()
