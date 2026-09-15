from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from sih26168_alignment.frame_aligner import FrameAligner
from sih26168_alignment.simulator import generate_scenario, write_scenario_csv
from sih26168_alignment.types import OptionalGnssAid

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / "member2_alignment" / "tests" / "data" / "generated"


def _python_run(sc):
    al = FrameAligner()
    rows = []
    for i in range(sc.t.size):
        if sc.gnss_speed is not None and np.isfinite(sc.gnss_speed[i]):
            al.feed_gnss(
                OptionalGnssAid(
                    timestamp=float(sc.t[i]),
                    speed_mps=float(sc.gnss_speed[i]),
                    hdop=float(sc.gnss_hdop[i]),
                    num_sats=int(sc.gnss_sats[i]),
                )
            )
        f = al.process(
            float(sc.t[i]),
            *[float(x) for x in sc.acc_p[i]],
            *[float(x) for x in sc.gyro_p[i]],
        )
        rows.append(
            [
                f.timestamp,
                f.ax_v,
                f.ay_v,
                f.az_v,
                f.gx_v,
                f.gy_v,
                f.gz_v,
                *f.q_pv.tolist(),
                int(f.status),
                f.confidence.overall,
                f.confidence.gravity,
                f.confidence.yaw_observability,
            ]
        )
    return np.asarray(rows)


def _find_csv_aligner() -> Path | None:
    env = os.environ.get("MEMBER2_CSV_ALIGNER")
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        ROOT / "build" / "member2_alignment" / "member2_csv_aligner",
        ROOT / "build" / "member2_csv_aligner",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


@pytest.mark.parametrize("name", ["gnss_assisted", "stationary_phone", "straight_acceleration"])
def test_python_cpp_equivalence(name, tmp_path):
    exe = _find_csv_aligner()
    if exe is None:
        pytest.skip("member2_csv_aligner not built")
    sc = generate_scenario(name)
    csv_in = tmp_path / f"{name}.csv"
    csv_out = tmp_path / f"{name}_cpp.csv"
    write_scenario_csv(str(csv_in), sc)
    subprocess.check_call([str(exe), str(csv_in), str(csv_out)])
    py = _python_run(sc)
    cpp = np.loadtxt(csv_out, delimiter=",", skiprows=1)
    assert py.shape[0] == cpp.shape[0]
    # aligned accel/gyro
    assert np.allclose(py[:, 1:7], cpp[:, 1:7], atol=1e-6, rtol=1e-6)
    # quaternion (sign already canonicalized)
    assert np.allclose(py[:, 7:11], cpp[:, 7:11], atol=1e-6, rtol=1e-6)
    assert np.array_equal(py[:, 11].astype(int), cpp[:, 11].astype(int))
    assert np.allclose(py[:, 12:15], cpp[:, 12:15], atol=1e-5, rtol=1e-5)
