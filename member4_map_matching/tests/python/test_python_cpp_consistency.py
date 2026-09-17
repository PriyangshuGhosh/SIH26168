"""Cross-check Python and C++ roadpack outputs when the C++ binary is available."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from sih26168_map_matching.map_matcher import MapMatcher
from sih26168_map_matching.road_graph import build_synthetic_grid, write_roadpack
from sih26168_map_matching.types import NavigationState


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(
    shutil.which("member4_cpp_tests") is None
    and not (ROOT / "build" / "member4_map_matching" / "member4_cpp_tests").exists()
    and not (ROOT / "build" / "member4_cpp_tests").exists(),
    reason="C++ member4 tests binary not built",
)
def test_python_cpp_both_on_road_near_corridor(tmp_path):
    # Consistency of contract: both should mark near-road eastbound as on-road.
    network = build_synthetic_grid()
    pack = tmp_path / "grid.roadpack"
    write_roadpack(network, pack)
    matcher = MapMatcher(network)
    lat0, lon0 = 12.9716, 77.5946
    dlon = 5.0 / (111320.0 * math.cos(math.radians(lat0)))
    states = [
        NavigationState(
            float(i),
            lat0,
            lon0 + i * dlon,
            yaw_rad=math.pi / 2,
            position_cov_m2=((16.0, 0.0), (0.0, 16.0)),
        )
        for i in range(12)
    ]
    outs = matcher.match_trajectory(states)
    assert sum(1 for o in outs if o.is_on_road_network) >= 8

    binary = ROOT / "build" / "member4_map_matching" / "member4_cpp_tests"
    if not binary.exists():
        binary = ROOT / "build" / "member4_cpp_tests"
    env = os.environ.copy()
    env["MEMBER4_ROADPACK"] = str(pack)
    proc = subprocess.run(
        [str(binary)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
