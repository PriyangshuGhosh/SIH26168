#!/usr/bin/env python3
"""REAL-data GNSS-blackout positional-drift benchmark: real recorded IMU + real recorded GPS
ground truth from the official IO-VNBD dataset (recovered by
member1-ml/scripts/recover_iovnbd_gnss.py into member1-ml/data/derived/gnss_reference.npz), run
through the real M2 (FrameAligner) -> M1 (streaming GRU) -> M3 (EKF) chain.

Unlike member5_engine/scripts/gnss_blackout_benchmark.py (synthetic trajectory, since no position
ground truth was available at all in the originally-committed dataset), this is the real GNSS-tagged
trajectory validation: both the IMU driving it and the GPS ground truth it is checked against are
real recordings of the same physical drive, not synthesized.

Causality / no-leakage guarantee: the estimator (FrameAligner + GRU + EKF) is fed only IMU
(acc/gyr, same as M1's training input) and, outside the blackout window, real GPS fixes via the
normal GNSS-aiding channel. During the blackout window, no GNSS call is made at all -- the EKF has
no code path that can see it. Ground truth (recovered GPS lat/lon) is used only afterwards, to
compute the error metrics.

Usage (from member1-ml/):
    python ../member5_engine/scripts/real_data_blackout_benchmark.py \\
        --session S2__s01 --blackout-start-s 3000 --blackout-duration-s 600 \\
        --gru-checkpoint experiments/m1_gru_stream2_gru_w20/best.pt
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "member2_alignment" / "python"))
sys.path.insert(0, str(REPO / "member3_fusion" / "python"))
sys.path.insert(0, str(REPO / "member1-ml"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sih26168_alignment.frame_aligner import FrameAligner  # noqa: E402
from sih26168_alignment.types import CalibrationStatus, FrameAlignerConfig, OptionalGnssAid  # noqa: E402

from gnss_blackout_benchmark import EKFWithGnssPosition, SpeedGuard  # noqa: E402
from reference_ekf import Config as EKFConfig  # noqa: E402

EARTH_R = 6378137.0


def local_enu(lat, lon, lat0, lon0):
    lat0_rad = math.radians(lat0)
    north = math.radians(lat - lat0) * EARTH_R
    east = math.radians(lon - lon0) * EARTH_R * math.cos(lat0_rad)
    return north, east


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--npz", default=str(REPO / "member1-ml" / "data" / "member1_imu_speed.npz"))
    p.add_argument("--gnss-ref", default=str(REPO / "member1-ml" / "data" / "derived" / "gnss_reference.npz"))
    p.add_argument("--session", required=True)
    p.add_argument("--gru-checkpoint", default=str(REPO / "member1-ml" / "experiments" /
                                                     "m1_gru_stream2_gru_w20" / "best.pt"))
    p.add_argument("--warmup-s", type=float, default=30.0, help="GNSS-aided seconds before blackout starts")
    p.add_argument("--blackout-start-s", type=float, required=True, help="session-relative time (s)")
    p.add_argument("--blackout-duration-s", type=float, required=True)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    import torch
    from src.training.train import load_checkpoint

    d = np.load(args.npz, allow_pickle=True)  # read-only; never written
    sid = d["session_id"]
    mask = sid == args.session
    if not mask.any():
        print(f"session {args.session} not found in {args.npz}", file=sys.stderr)
        return 1
    acc = d["acc"][mask].astype(np.float64)
    gyr = d["gyr"][mask].astype(np.float64)
    n = len(acc)
    t = np.arange(n) * 0.1  # real native 10 Hz cadence (data_protocol.md)

    g = np.load(args.gnss_ref, allow_pickle=True)
    key = f"{args.session}/lat"
    if key not in g:
        print(f"no recovered GNSS reference for session {args.session} in {args.gnss_ref}", file=sys.stderr)
        return 1
    lat = g[f"{args.session}/lat"]
    lon = g[f"{args.session}/lon"]
    gps_speed = g[f"{args.session}/gps_speed_mps"]
    lat0, lon0 = float(lat[0]), float(lon[0])
    true_n = np.zeros(n)
    true_e = np.zeros(n)
    for i in range(n):
        true_n[i], true_e[i] = local_enu(lat[i], lon[i], lat0, lon0)

    model, _ = load_checkpoint(args.gru_checkpoint, map_location="cpu")
    model.eval()

    aligner = FrameAligner(FrameAlignerConfig(sample_rate_hz=10.0))
    ekf = EKFWithGnssPosition(EKFConfig())
    ai_guard = SpeedGuard()
    h = torch.zeros(model.gru_layers, 1, model.gru_hidden)

    blackout_start = args.blackout_start_s
    blackout_end = blackout_start + args.blackout_duration_s
    last_fix_lat, last_fix_lon = None, None

    log_t, log_est_n, log_est_e, log_true_n, log_true_e, log_blackout, log_is_fix = ([] for _ in range(7))

    for i in range(n):
        ti = float(t[i])
        ax, ay, az = acc[i]
        gx, gy, gz = gyr[i]
        aligned = aligner.process(ti, ax, ay, az, gx, gy, gz)
        fully_aligned = aligned.status == CalibrationStatus.FULLY_ALIGNED
        in_blackout = blackout_start <= ti < blackout_end

        if aligned.status != CalibrationStatus.INVALID:
            ekf.predict(ti, aligned.ax_v, aligned.ay_v, aligned.gz_v, fully_aligned=fully_aligned)

            if not fully_aligned:
                h = torch.zeros(model.gru_layers, 1, model.gru_hidden)
            else:
                ch = [aligned.ax_v, aligned.ay_v, aligned.az_v, aligned.gx_v, aligned.gy_v, aligned.gz_v]
                x_t = torch.tensor([[ch]], dtype=torch.float32)
                with torch.no_grad():
                    mean, log_var, h = model.step(x_t, h)
                velocity = max(0.0, float(mean.item()))
                variance = float(torch.exp(log_var).item()) if log_var is not None else 0.05
                if ai_guard.accept_ai(ti, velocity, variance):
                    ekf.update_speed(ti, velocity, max(variance, 1e-4))

        # Real GPS fix cadence: this log holds the last real fix constant between actual updates
        # (typical phone GPS logging), so "lat/lon changed from the previous row" is the genuine
        # new-fix event -- both for feeding the estimator (never during blackout: the causal
        # no-leakage guarantee, see module docstring) and, later, for evaluation: only real fix
        # points are valid ground-truth waypoints, the held-constant rows between them are not a
        # real continuous position and must not be treated as one (see "Real GPS fix granularity"
        # note below).
        is_new_fix = (np.isfinite(lat[i]) and np.isfinite(lon[i]) and
                      (last_fix_lat is None or lat[i] != last_fix_lat or lon[i] != last_fix_lon))
        if is_new_fix:
            last_fix_lat, last_fix_lon = lat[i], lon[i]
            if not in_blackout:
                aligner.feed_gnss(OptionalGnssAid(timestamp=ti, speed_mps=float(max(0.0, gps_speed[i])),
                                                  hdop=1.5, num_sats=10))
                ekf.update_gnss_position(true_n[i], true_e[i], 6.0)
                if np.isfinite(gps_speed[i]):
                    ekf.update_speed(ti, float(max(0.0, gps_speed[i])), 0.25)

        log_t.append(ti)
        log_est_n.append(float(ekf.x[0]))
        log_est_e.append(float(ekf.x[1]))
        log_true_n.append(true_n[i])
        log_true_e.append(true_e[i])
        log_blackout.append(in_blackout)
        log_is_fix.append(is_new_fix)

    log_t = np.array(log_t)
    est_n, est_e = np.array(log_est_n), np.array(log_est_e)
    tn, te = np.array(log_true_n), np.array(log_true_e)
    bo = np.array(log_blackout)
    is_fix = np.array(log_is_fix)

    # Real GPS fix granularity: this recording's actual fix rate is far below 10 Hz (held-constant
    # between updates -- see module docstring), so error/distance are computed ONLY at genuine
    # fix rows, never on the artificially-upsampled 10 Hz staircase (that would silently treat a
    # stale, repeated GPS value as if it were a fresh high-rate ground truth -- fabrication).
    eval_idx = np.flatnonzero(is_fix)
    log_t, est_n, est_e, tn, te, bo = (a[eval_idx] for a in (log_t, est_n, est_e, tn, te, bo))
    err = np.hypot(est_n - tn, est_e - te)

    bo_idx = np.where(bo)[0]
    if bo_idx.size == 0:
        print("blackout window had no samples (out of range for this session)", file=sys.stderr)
        return 1
    i0 = bo_idx[0]
    seg = np.hypot(np.diff(tn[i0:]), np.diff(te[i0:]))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    err_bo = err[i0:]

    def checkpoint(target_m):
        if cum[-1] < target_m:
            j = len(cum) - 1
        else:
            j = int(np.searchsorted(cum, target_m))
            j = min(j, len(cum) - 1)
        return {
            "target_m": target_m, "blackout_distance_m": float(cum[j]),
            "final_position_error_m": float(err_bo[j]), "max_position_error_m": float(err_bo[:j + 1].max()),
            "drift_pct": float(err_bo[j] / cum[j] * 100.0) if cum[j] > 1e-6 else None,
        }

    summary = {
        "session": args.session, "n_samples": n, "blackout_start_s": blackout_start,
        "blackout_duration_s": args.blackout_duration_s, "blackout_total_distance_m": float(cum[-1]),
        "checkpoints": {"50m": checkpoint(50.0), "1km": checkpoint(1000.0), "end_of_blackout": checkpoint(cum[-1])},
        "data_source": "real recorded IMU + real recovered GPS (official IO-VNBD, see "
                       "member1-ml/scripts/recover_iovnbd_gnss.py)",
    }
    print(json.dumps(summary, indent=2, default=str))
    if args.out:
        Path(args.out).write_text(json.dumps({
            **summary,
            "t": log_t.tolist(), "est_n": est_n.tolist(), "est_e": est_e.tolist(),
            "true_n": tn.tolist(), "true_e": te.tolist(), "blackout": bo.tolist(),
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
