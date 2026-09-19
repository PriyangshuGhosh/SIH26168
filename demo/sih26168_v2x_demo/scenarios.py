"""Deterministic demo scenario presets. SIMULATION only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoSpec:
    name: str
    n_remotes: int = 3
    seed: int = 7
    dt_s: float = 0.1
    packet_loss: float = 0.0
    latency_mean_s: float = 0.05
    latency_jitter_s: float = 0.01
    out_of_order_rate: float = 0.0
    gnss_outage_s: float | None = None
    gnss_restore_s: float | None = None
    inject_bad_at_s: float | None = None
    bad_offset_east_m: float = 400.0
    pos_std_m: float = 2.5
    demo_mode: bool = False
    duration_s: float = 50.0


RECORDING_TIMELINE = (
    (0.0, "We are navigating normally."),
    (10.0, "GNSS is lost."),
    (12.0, "Our vehicle keeps moving without GNSS."),
    (15.0, "Nearby cars send cooperative V2X notes."),
    (20.0, "A bad observation appears."),
    (21.0, "NIS gate: the bad note is rejected."),
    (27.0, "Navigation keeps going."),
    (40.0, "Final error: baseline vs V2X-assisted."),
)


def recording_spec() -> DemoSpec:
    """Fixed seed/timing for a 50 s screen recording."""
    return DemoSpec(
        name="recording",
        n_remotes=3,
        seed=7,
        dt_s=0.1,
        packet_loss=0.02,
        latency_mean_s=0.05,
        latency_jitter_s=0.008,
        gnss_outage_s=10.0,
        gnss_restore_s=None,
        inject_bad_at_s=20.0,
        demo_mode=True,
        duration_s=50.0,
    )


SCENARIO_PRESETS: dict[str, DemoSpec] = {
    "normal": DemoSpec(name="normal", n_remotes=3, seed=7, gnss_outage_s=None),
    "gnss_outage": DemoSpec(name="gnss_outage", n_remotes=0, seed=7, gnss_outage_s=10.0),
    "outage_1": DemoSpec(name="outage_1", n_remotes=1, seed=7, gnss_outage_s=10.0),
    "outage_3": DemoSpec(name="outage_3", n_remotes=3, seed=7, gnss_outage_s=10.0),
    "outage_10": DemoSpec(name="outage_10", n_remotes=10, seed=7, gnss_outage_s=10.0),
    "outage_bad": DemoSpec(
        name="outage_bad",
        n_remotes=3,
        seed=7,
        gnss_outage_s=10.0,
        inject_bad_at_s=20.0,
    ),
    "degraded_comms": DemoSpec(
        name="degraded_comms",
        n_remotes=3,
        seed=11,
        packet_loss=0.35,
        latency_mean_s=0.18,
        latency_jitter_s=0.06,
        out_of_order_rate=0.08,
        gnss_outage_s=10.0,
    ),
    "recording": recording_spec(),
}


def caption_at(t: float) -> str:
    text = RECORDING_TIMELINE[0][1]
    for ts, cap in RECORDING_TIMELINE:
        if t + 1e-9 >= ts:
            text = cap
    return text
