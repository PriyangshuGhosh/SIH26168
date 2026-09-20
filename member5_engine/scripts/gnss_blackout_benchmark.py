#!/usr/bin/env python3
"""GNSS-blackout positional-drift benchmark for the real M2 -> M1 -> M3 dead-reckoning chain.

Measures the SIH26168 acceptance criterion -- positional drift during a GNSS blackout must be
< 10% of the distance travelled during the blackout -- using the project's REAL Python components:

  * ``sih26168_alignment.frame_aligner.FrameAligner`` (Member 2, production Python reference)
  * ``experiments/production2_cnn_mag_w20/final.production.onnx`` via onnxruntime (the actual
    committed production Member 1 model, not a mock)
  * ``member1-ml/src/inference/member2_interface.ProductionWindowBuffer`` (the real causal
    100 Hz -> windowed-10 Hz production interface)
  * ``member3_fusion/python/reference_ekf.EKFReference`` (Member 3, NumPy mirror of
    ``EKFFusionEngine.cpp``'s exact prediction/update equations)

No compiled C++ binary is required, so this runs in any environment with Python + onnxruntime.

Ground truth
------------
No real GPS-tagged driving recording exists in this repository (the only committed real dataset,
``member1-ml/data/member1_imu_speed.npz``, has real accelerometer/gyroscope/speed but no
latitude/longitude). A genuine positional-drift number therefore needs a *known* reference path;
this script synthesizes one (fixed speed/turn profile -> true north/east/yaw) and generates
phone-frame IMU consistent with it under an arbitrary, fixed, UNKNOWN-TO-THE-PIPELINE mounting
rotation, exactly like the project's own ``member5_engine/tools/synthetic_e2e.cpp`` and
``sih26168_alignment.simulator`` conventions. Sensor noise/bias magnitudes are empirically grounded
in the real dataset's near-stationary segments (see ``_measure_real_noise()``), not guessed.

This is a SIMULATION result, not a real-world field trial -- it is reported as such, matching this
repo's existing "SYNTHETIC VALIDATION ONLY" convention (see docs/member4/STATUS.md).

Causality guarantee
--------------------
The simulation is a single forward pass over time. During a blackout window, ``feed_gnss`` below is
simply never called -- the EKF has no code path that can see a future or blacked-out GNSS sample.
Ground truth (``true_north/true_east/...``) is used only afterwards, to compute error metrics; it is
never passed to FrameAligner, the ONNX model, or the EKF.

Usage
-----
    python member5_engine/scripts/gnss_blackout_benchmark.py \\
        --onnx experiments/production2_cnn_mag_w20/final.production.onnx \\
        [--seed 26168] [--out /path/to/report.json]

Run from ``member1-ml/`` (so the ``--onnx`` default resolves) or pass an absolute ``--onnx`` path.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "member2_alignment" / "python"))
sys.path.insert(0, str(REPO / "member3_fusion" / "python"))
sys.path.insert(0, str(REPO / "member1-ml"))

from sih26168_alignment.frame_aligner import FrameAligner  # noqa: E402
from sih26168_alignment.frames import rotation_zyx, vehicleToPhoneVector  # noqa: E402
from sih26168_alignment.types import CalibrationStatus, FrameAlignerConfig, OptionalGnssAid  # noqa: E402

from reference_ekf import Config as EKFConfig, EKFReference  # noqa: E402

from src.inference.member2_interface import ProductionWindowBuffer  # noqa: E402

G = 9.80665
DT = 0.01  # 100 Hz


# --------------------------------------------------------------------------------------- ground truth


@dataclass
class TrajectoryConfig:
    static_end_s: float = 3.0
    accel_end_s: float = 10.0
    cruise_mps: float = 12.0
    blackout_start_s: float = 60.0
    blackout_duration_s: float = 96.0
    # Two turns: one BEFORE the blackout (e.g. turning onto the road that leads into a tunnel --
    # ordinary and realistic) so Member 2's turn-based yaw-sign disambiguation
    # (see FrameAligner._update_yaw's "Turn-based 180 deg disambiguation") gets a chance to fire
    # pre-blackout like it would on a real drive, and one DURING the blackout so the drift
    # measurement itself is not limited to an unrealistic dead-straight road.
    turn_starts_s: tuple = (20.0, 100.0)
    turn_duration_s: float = 5.0
    # Peak yaw rate must clear Member 2's yaw_turn_gyro_min (0.20 rad/s) to register as a
    # disambiguating turn at all -- 0.35 rad/s (~20 deg/s peak) is a normal, unhurried
    # intersection turn, comfortably above that gate without being an aggressive maneuver.
    turn_peak_rate_rps: float = 0.35
    reacquire_tail_s: float = 10.0
    gnss_hz: float = 1.0

    @property
    def total_s(self) -> float:
        return self.blackout_start_s + self.blackout_duration_s + self.reacquire_tail_s


def speed_at(t: float, cfg: TrajectoryConfig) -> float:
    if t < cfg.static_end_s:
        return 0.0
    if t < cfg.accel_end_s:
        a = cfg.cruise_mps / (cfg.accel_end_s - cfg.static_end_s)
        return a * (t - cfg.static_end_s)
    base = cfg.cruise_mps
    # Natural cruise-speed variation (not a constant, artificial-looking plateau). Amplitude/period
    # chosen so peak along-track accel (~0.63 m/s^2) periodically exceeds Member 2's
    # yaw_min_horiz_accel gate (0.45 m/s^2, see FrameAlignerConfig) -- ordinary following-traffic
    # speed changes do this constantly in real driving; a perfectly smooth cruise would not, and
    # would starve Member 2 of the periodic yaw re-confirmation evidence real driving provides.
    return max(0.0, base + 0.8 * math.sin(2.0 * math.pi * t / 8.0))


def accel_at(t: float, cfg: TrajectoryConfig, h: float = 1e-3) -> float:
    return (speed_at(t + h, cfg) - speed_at(t - h, cfg)) / (2.0 * h)


def yaw_rate_at(t: float, cfg: TrajectoryConfig) -> float:
    for turn_start in cfg.turn_starts_s:
        te = turn_start + cfg.turn_duration_s
        if turn_start <= t < te:
            phase = (t - turn_start) / cfg.turn_duration_s
            return cfg.turn_peak_rate_rps * math.sin(math.pi * phase)
    return 0.0


def _measure_real_noise() -> dict:
    """Empirical PER-AXIS accel/gyro noise std from the real IO-VNBD-derived dataset's
    near-stationary samples (target_speed_mps < 0.3), so injected sensor noise is not an
    arbitrary guess. Per-axis (not an isotropic average) matters: the real Z-accelerometer axis
    is markedly quieter than X/Y (gravity-dominated), so averaging the three would over-inflate
    injected Z noise and distort the accelerometer-norm signal used for static detection."""
    npz = REPO / "member1-ml" / "data" / "member1_imu_speed.npz"
    default = {"acc_std": np.array([0.30, 0.30, 0.30]), "gyro_std": np.array([0.02, 0.02, 0.02])}
    if not npz.exists():
        return default
    d = np.load(npz, allow_pickle=True)
    mask = d["target_speed_mps"] < 0.3
    if mask.sum() < 100:
        return default
    acc = d["acc"][mask]
    gyr = d["gyr"][mask]
    return {"acc_std": acc.std(axis=0), "gyro_std": gyr.std(axis=0)}


def generate_truth(cfg: TrajectoryConfig, rng: np.random.Generator, noise: dict):
    """Forward-integrate a known vehicle-frame trajectory and the phone-frame IMU consistent
    with it under a fixed, arbitrary mounting rotation. Returns per-sample arrays."""
    n = int(round(cfg.total_s / DT)) + 1
    t = np.arange(n) * DT

    true_yaw = np.zeros(n)
    true_north = np.zeros(n)
    true_east = np.zeros(n)
    true_speed = np.zeros(n)
    ax_v_true = np.zeros(n)
    ay_v_true = np.zeros(n)
    gz_v_true = np.zeros(n)

    yaw = 0.0
    north = 0.0
    east = 0.0
    for i in range(n):
        ti = t[i]
        v = speed_at(ti, cfg)
        wz = yaw_rate_at(ti, cfg)
        a_along = accel_at(ti, cfg)
        true_speed[i] = v
        true_yaw[i] = yaw
        true_north[i] = north
        true_east[i] = east
        ax_v_true[i] = a_along
        ay_v_true[i] = wz * v  # coordinated turn, NHC-consistent (vy ~ 0 in vehicle frame)
        gz_v_true[i] = wz
        if i + 1 < n:
            yaw = yaw + wz * DT
            north = north + v * math.cos(yaw) * DT - 0.0 * math.sin(yaw) * DT
            east = east + v * math.sin(yaw) * DT + 0.0 * math.cos(yaw) * DT

    az_v_true = np.full(n, G)

    # Fixed, arbitrary phone mount -- unknown to Member 2, exactly like production.
    R_vp = rotation_zyx(0.55, -0.22, 0.33)

    acc_v_true = np.stack([ax_v_true, ay_v_true, az_v_true], axis=1)
    gyro_v_true = np.stack([np.zeros(n), np.zeros(n), gz_v_true], axis=1)

    acc_p = np.zeros_like(acc_v_true)
    gyro_p = np.zeros_like(gyro_v_true)
    for i in range(n):
        acc_p[i] = vehicleToPhoneVector(R_vp, acc_v_true[i])
        gyro_p[i] = vehicleToPhoneVector(R_vp, gyro_v_true[i])

    acc_std = noise["acc_std"]
    gyro_std = noise["gyro_std"]
    acc_bias_p = np.array([0.08, -0.05, 0.05])
    gyro_bias_p = np.array([0.015, -0.01, 0.02])
    acc_p = acc_p + acc_bias_p + rng.normal(0.0, acc_std, size=acc_p.shape)
    gyro_p = gyro_p + gyro_bias_p + rng.normal(0.0, gyro_std, size=gyro_p.shape)

    return {
        "t": t,
        "true_yaw": true_yaw,
        "true_north": true_north,
        "true_east": true_east,
        "true_speed": true_speed,
        "acc_p": acc_p,
        "gyro_p": gyro_p,
        "R_vp": R_vp,
    }


def gnss_blacked_out(t: float, cfg: TrajectoryConfig) -> bool:
    return cfg.blackout_start_s <= t < (cfg.blackout_start_s + cfg.blackout_duration_s)


# --------------------------------------------------------------------------------------- AI-speed guard


@dataclass
class SpeedGuardConfig:
    max_vehicle_speed_mps: float = 55.0
    max_speed_change_mps_per_second: float = 12.0
    min_speed_variance_m2s2: float = 0.04
    max_speed_variance_m2s2: float = 2500.0


@dataclass
class SpeedGuard:
    """Mirrors member5_engine/src/SpeedValidity.cpp's SpeedValidityFilter exactly (jump/variance
    gating applied to the AI-speed measurement before it reaches the EKF)."""

    cfg: SpeedGuardConfig = field(default_factory=SpeedGuardConfig)
    have_trusted: bool = False
    last_speed: float = 0.0
    last_t: float = 0.0

    def accept_ai(self, t: float, speed: float, variance: float) -> bool:
        if not (math.isfinite(variance) and self.cfg.min_speed_variance_m2s2 <= variance <= self.cfg.max_speed_variance_m2s2):
            return False
        if not (math.isfinite(speed) and speed >= 0.0):
            return False
        if speed > self.cfg.max_vehicle_speed_mps:
            return False
        if self.have_trusted:
            dt = t - self.last_t
            if dt < 0.0 or not math.isfinite(dt):
                return False
            if dt > 0.0:
                dv = abs(speed - self.last_speed)
                if dv > self.cfg.max_speed_change_mps_per_second * dt and dv > 1.0:
                    return False
        self.last_speed = speed
        self.last_t = t
        self.have_trusted = True
        return True


# --------------------------------------------------------------------------------------- EKF + GNSS position


class EKFWithGnssPosition(EKFReference):
    """Adds the 2-D GNSS position update that reference_ekf.py intentionally leaves out (its
    docstring only claims to mirror prediction/NHC/scalar-speed). Mirrors
    EKFFusionEngine.cpp::updatePositionMeasurementGated exactly: same H, R floor, NIS gate,
    Joseph-form covariance update."""

    def __init__(self, config=None, gnss_position_sigma_floor_m: float = 1.0,
                 gnss_nis_threshold: float = 5.991):
        super().__init__(config)
        self.gnss_position_sigma_floor_m = gnss_position_sigma_floor_m
        self.gnss_nis_threshold = gnss_nis_threshold

    def update_gnss_position(self, north: float, east: float, sigma_m: float) -> bool:
        H = np.zeros((2, 8))
        H[0, 0] = H[1, 1] = 1.0
        safe = max(sigma_m * sigma_m, self.gnss_position_sigma_floor_m ** 2)
        R = np.eye(2) * safe
        innovation = np.array([north - self.x[0], east - self.x[1]])
        S = H @ self.P @ H.T + R
        if not np.isfinite(S).all():
            return False
        try:
            solved = np.linalg.solve(S, innovation)
        except np.linalg.LinAlgError:
            return False
        if not np.isfinite(solved).all():
            return False
        nis = float(innovation @ solved)
        if not math.isfinite(nis) or nis > self.gnss_nis_threshold:
            return False
        K = self.P @ H.T @ np.linalg.inv(S)
        A = np.eye(8) - K @ H
        self.x = self.x + K @ innovation
        self.P = A @ self.P @ A.T + K @ R @ K.T
        self.x[4] = self._yaw(self.x[4])
        return self._stabilize() and np.isfinite(self.x).all()


# --------------------------------------------------------------------------------------- pipeline run


class OnnxWindowedSpeedSource:
    """Existing production path: real committed ONNX model, 200-sample/2 s causal window,
    buffered by the real ``ProductionWindowBuffer`` (stateless between windows)."""

    def __init__(self, onnx_path: Path):
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.buf = ProductionWindowBuffer()

    def maybe_predict(self, aligned):
        pushed = self.buf.push(aligned)
        if pushed is None:
            return None
        window, win_t = pushed
        x = window[None, :, :].astype(np.float32)
        outputs = self.session.run(self.output_names, {self.input_name: x})
        out = dict(zip(self.output_names, outputs))
        velocity = float(np.ravel(out.get("velocity_mps", outputs[0]))[0])
        variance = float(np.ravel(out.get("velocity_variance_m2s2", [0.05]))[0])
        return win_t, velocity, variance


class GruStreamingSpeedSource:
    """New candidate: the session-TBPTT-trained streaming GRU (scripts/train_gru_streaming.py),
    called via VelocityNet.step() with hidden state persisted across the WHOLE run (reset only on
    an M2 discontinuity -- non-FULLY_ALIGNED -- exactly like ProductionWindowBuffer.reset()), at the
    same effective 10 Hz production cadence (every DECIMATION_FACTOR-th aligned sample), but with NO
    200-sample cold-start latency, since there is no fixed window to fill."""

    def __init__(self, checkpoint_path: Path):
        import torch
        from src.training.train import load_checkpoint

        self.torch = torch
        self.model, _ = load_checkpoint(str(checkpoint_path), map_location="cpu")
        self.model.eval()
        self.h = torch.zeros(self.model.gru_layers, 1, self.model.gru_hidden)
        self._stride_count = 0
        self._decimation = 10

    def maybe_predict(self, aligned):
        if aligned.status.name != "FULLY_ALIGNED":
            self.h = self.torch.zeros(self.model.gru_layers, 1, self.model.gru_hidden)
            self._stride_count = 0
            return None
        self._stride_count += 1
        if self._stride_count < self._decimation:
            return None
        self._stride_count = 0
        ch = [aligned.ax_v, aligned.ay_v, aligned.az_v, aligned.gx_v, aligned.gy_v, aligned.gz_v]
        x_t = self.torch.tensor([[ch]], dtype=self.torch.float32)
        with self.torch.no_grad():
            mean, log_var, self.h = self.model.step(x_t, self.h)
        velocity = max(0.0, float(mean.item()))
        variance = float(self.torch.exp(log_var).item()) if log_var is not None else 0.05
        return float(aligned.timestamp), velocity, variance


def run_pipeline(cfg: TrajectoryConfig, m1_source, seed: int = 26168):
    rng = np.random.default_rng(seed)
    noise = _measure_real_noise()
    truth = generate_truth(cfg, rng, noise)
    n = truth["t"].shape[0]

    aligner = FrameAligner(FrameAlignerConfig())
    ekf = EKFWithGnssPosition(EKFConfig())
    ai_guard = SpeedGuard()

    gnss_rng = np.random.default_rng(seed + 1)
    gnss_sigma_true_m = 3.0
    gnss_speed_sigma_true = 0.3
    gnss_hdop = 1.2

    last_gnss_fire = -1.0

    log_t, log_est_n, log_est_e, log_true_n, log_true_e, log_dr, log_conf = ([] for _ in range(7))

    for i in range(n):
        t = float(truth["t"][i])
        ax_p, ay_p, az_p = truth["acc_p"][i]
        gx_p, gy_p, gz_p = truth["gyro_p"][i]

        aligned = aligner.process(t, ax_p, ay_p, az_p, gx_p, gy_p, gz_p)
        fully_aligned = aligned.status == CalibrationStatus.FULLY_ALIGNED

        if aligned.status != CalibrationStatus.INVALID:
            ekf.predict(t, aligned.ax_v, aligned.ay_v, aligned.gz_v, fully_aligned=fully_aligned)

            pred = m1_source.maybe_predict(aligned)
            if pred is not None:
                win_t, velocity, variance = pred
                if ai_guard.accept_ai(win_t, velocity, variance):
                    ekf.update_speed(win_t, velocity, max(variance, 1e-4))

        blackout = gnss_blacked_out(t, cfg)
        if not blackout and (t - last_gnss_fire) >= (1.0 / cfg.gnss_hz - 1e-6):
            last_gnss_fire = t
            meas_n = truth["true_north"][i] + gnss_rng.normal(0.0, gnss_sigma_true_m)
            meas_e = truth["true_east"][i] + gnss_rng.normal(0.0, gnss_sigma_true_m)
            meas_speed = max(0.0, truth["true_speed"][i] + gnss_rng.normal(0.0, gnss_speed_sigma_true))
            sigma = max(1.0, gnss_hdop * 5.0)
            # Mirrors Engine.cpp::handleGnss, which always feeds an accepted GNSS fix to BOTH
            # Member 2 (yaw-sign disambiguation -- see docs/member2/INTEGRATION.md) and Member 3,
            # not only the EKF. Omitting this call (an earlier version of this harness did) starves
            # FrameAligner of the sign evidence it needs to ever reach FULLY_ALIGNED on a straight
            # road, which then silently disables Member 1 AI-speed updates and Member 3's NHC for
            # the whole run -- a harness-fidelity bug, not a production one.
            aligner.feed_gnss(OptionalGnssAid(timestamp=t, speed_mps=meas_speed, hdop=gnss_hdop,
                                               num_sats=10))
            ekf.update_gnss_position(meas_n, meas_e, sigma)
            ekf.update_speed(t, meas_speed, max(0.25, 0.05 * sigma * sigma))

        if i % 10 == 0:
            log_t.append(t)
            log_est_n.append(float(ekf.x[0]))
            log_est_e.append(float(ekf.x[1]))
            log_true_n.append(float(truth["true_north"][i]))
            log_true_e.append(float(truth["true_east"][i]))
            log_dr.append(blackout)
            log_conf.append(float(aligned.confidence.overall))

    return {
        "t": np.array(log_t),
        "est_n": np.array(log_est_n),
        "est_e": np.array(log_est_e),
        "true_n": np.array(log_true_n),
        "true_e": np.array(log_true_e),
        "blackout": np.array(log_dr),
        "noise": noise,
        "cfg": cfg,
    }


# --------------------------------------------------------------------------------------- metrics


def summarize(result: dict) -> dict:
    cfg: TrajectoryConfig = result["cfg"]
    t = result["t"]
    est_n, est_e = result["est_n"], result["est_e"]
    true_n, true_e = result["true_n"], result["true_e"]
    err = np.hypot(est_n - true_n, est_e - true_e)

    in_bo = result["blackout"]
    idx_bo = np.where(in_bo)[0]
    if idx_bo.size == 0:
        return {"error": "no blackout samples logged"}
    bo_start_idx = idx_bo[0]

    # True cumulative distance travelled since blackout start (arclength of the true path).
    seg = np.hypot(np.diff(true_n[bo_start_idx:]), np.diff(true_e[bo_start_idx:]))
    cum_true_dist = np.concatenate([[0.0], np.cumsum(seg)])
    # Estimated cumulative distance (arclength of the estimated path) over the same window.
    seg_est = np.hypot(np.diff(est_n[bo_start_idx:]), np.diff(est_e[bo_start_idx:]))
    cum_est_dist = np.concatenate([[0.0], np.cumsum(seg_est)])
    err_bo = err[bo_start_idx:]
    t_bo = t[bo_start_idx:]

    def checkpoint(target_m: float):
        if cum_true_dist[-1] < target_m:
            j = len(cum_true_dist) - 1
        else:
            j = int(np.searchsorted(cum_true_dist, target_m))
            j = min(j, len(cum_true_dist) - 1)
        return {
            "target_m": target_m,
            "blackout_distance_m": float(cum_true_dist[j]),
            "estimated_distance_m": float(cum_est_dist[j]),
            "final_position_error_m": float(err_bo[j]),
            "max_position_error_m": float(err_bo[: j + 1].max()),
            "drift_pct": float(err_bo[j] / cum_true_dist[j] * 100.0) if cum_true_dist[j] > 1e-6 else None,
            "elapsed_s": float(t_bo[j] - t_bo[0]),
        }

    checkpoints = {"50m": checkpoint(50.0)}
    if cum_true_dist[-1] >= 999.0:
        checkpoints["1km"] = checkpoint(1000.0)
    else:
        checkpoints["1km"] = {
            "target_m": 1000.0,
            "note": f"blackout only covers {cum_true_dist[-1]:.1f} m of true travel; "
                    "reporting end-of-blackout instead",
            **checkpoint(cum_true_dist[-1]),
        }
    checkpoints["end_of_blackout"] = checkpoint(cum_true_dist[-1])

    error_vs_distance = [
        {"distance_m": float(d), "error_m": float(e)}
        for d, e in zip(cum_true_dist[:: max(1, len(cum_true_dist) // 60)],
                         err_bo[:: max(1, len(cum_true_dist) // 60)])
    ]

    return {
        "blackout_duration_s": cfg.blackout_duration_s,
        "blackout_total_distance_m": float(cum_true_dist[-1]),
        "checkpoints": checkpoints,
        "error_vs_distance": error_vs_distance,
        "noise_used": result["noise"],
    }


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        for c in (Path.cwd() / path, REPO / "member1-ml" / path):
            if c.exists():
                return c
    return path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--onnx", default="experiments/production2_cnn_mag_w20/final.production.onnx")
    p.add_argument("--m1-model", choices=["onnx", "gru-streaming"], default="onnx",
                   help="onnx: existing production windowed CNN. gru-streaming: new stateful GRU "
                        "candidate (scripts/train_gru_streaming.py checkpoint), passed via --gru-checkpoint")
    p.add_argument("--gru-checkpoint", default="experiments/m1_gru_stream2_gru_w20/best.pt")
    p.add_argument("--seed", type=int, default=26168)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    if args.m1_model == "onnx":
        onnx_path = _resolve(args.onnx)
        if not onnx_path.exists():
            print(f"ONNX model not found: {args.onnx}", file=sys.stderr)
            return 1
        m1_source = OnnxWindowedSpeedSource(onnx_path)
        model_id = str(onnx_path)
    else:
        ckpt_path = _resolve(args.gru_checkpoint)
        if not ckpt_path.exists():
            print(f"GRU checkpoint not found: {args.gru_checkpoint}", file=sys.stderr)
            return 1
        m1_source = GruStreamingSpeedSource(ckpt_path)
        model_id = str(ckpt_path)

    cfg = TrajectoryConfig()
    result = run_pipeline(cfg, m1_source, seed=args.seed)
    summary = summarize(result)
    summary["m1_model"] = args.m1_model
    summary["m1_checkpoint"] = model_id
    summary["seed"] = args.seed

    print(json.dumps(summary, indent=2, default=str))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
