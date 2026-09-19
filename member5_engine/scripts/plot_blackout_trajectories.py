"""Generate the GNSS-blackout position plot (reference vs. estimated trajectory, plus error-vs-
distance) comparing the production ONNX (CNN) and streaming-GRU M1 candidates on the same
synthetic scenario used by gnss_blackout_benchmark.py. See docs/gru_velocity.md.

Usage (from member1-ml/):
    python ../member5_engine/scripts/plot_blackout_trajectories.py --out-dir results/blackout_plots
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gnss_blackout_benchmark import (  # noqa: E402
    GruStreamingSpeedSource, OnnxWindowedSpeedSource, TrajectoryConfig, run_pipeline, summarize,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--onnx", default="experiments/production2_cnn_mag_w20/final.production.onnx")
    p.add_argument("--gru-checkpoint", default="experiments/m1_gru_stream2_gru_w20/best.pt")
    p.add_argument("--seed", type=int, default=26168)
    p.add_argument("--out-dir", default="results/blackout_plots")
    args = p.parse_args()

    cfg = TrajectoryConfig()
    onnx_path = Path(args.onnx)
    gru_path = Path(args.gru_checkpoint)

    result_cnn = run_pipeline(cfg, OnnxWindowedSpeedSource(onnx_path), seed=args.seed)
    result_gru = run_pipeline(cfg, GruStreamingSpeedSource(gru_path), seed=args.seed)
    summary_cnn = summarize(result_cnn)
    summary_gru = summarize(result_gru)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # -------- trajectory plot (north/east, meters) --------
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.plot(result_cnn["true_e"], result_cnn["true_n"], color="black", linewidth=2.2,
            label="Reference (ground truth) trajectory", zorder=5)
    bo = result_cnn["blackout"]
    bo_idx = np.where(bo)[0]
    if bo_idx.size:
        ax.plot(result_cnn["true_e"][bo_idx], result_cnn["true_n"][bo_idx], color="black",
                linewidth=5.0, alpha=0.15, zorder=1, label="GNSS blackout window")
    ax.plot(result_cnn["est_e"], result_cnn["est_n"], color="#d62728", linewidth=1.6, linestyle="--",
            label=f"Estimated (current: windowed CNN, 1 km drift {summary_cnn['checkpoints']['1km']['drift_pct']:.1f}%)")
    ax.plot(result_gru["est_e"], result_gru["est_n"], color="#1f77b4", linewidth=1.6,
            label=f"Estimated (new: streaming GRU, 1 km drift {summary_gru['checkpoints']['1km']['drift_pct']:.1f}%)")
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    ax.set_title("SIH26168: GNSS-blackout dead-reckoning trajectory\n(simulation-based, see docs/gru_velocity.md)")
    ax.legend(loc="best", fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "trajectory_reference_vs_estimated.png", dpi=160)
    plt.close(fig)

    # -------- error vs distance plot --------
    def err_vs_dist(result):
        t = result["t"]
        est_n, est_e = result["est_n"], result["est_e"]
        true_n, true_e = result["true_n"], result["true_e"]
        err = np.hypot(est_n - true_n, est_e - true_e)
        bo_idx = np.where(result["blackout"])[0]
        i0 = bo_idx[0]
        seg = np.hypot(np.diff(true_n[i0:]), np.diff(true_e[i0:]))
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        return cum, err[i0:]

    cum_cnn, err_cnn = err_vs_dist(result_cnn)
    cum_gru, err_gru = err_vs_dist(result_gru)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(cum_cnn, err_cnn, color="#d62728", linewidth=1.8, label="Current: windowed CNN")
    ax.plot(cum_gru, err_gru, color="#1f77b4", linewidth=1.8, label="New: streaming GRU")
    ax.axhline(0.0, color="gray", linewidth=0.8)
    ten_pct_cnn = 0.10 * cum_cnn
    ax.plot(cum_cnn, ten_pct_cnn, color="gray", linewidth=1.2, linestyle=":", label="10% SIH drift bound")
    ax.set_xlabel("Distance travelled since blackout start (m)")
    ax.set_ylabel("Position error (m)")
    ax.set_title("Position error vs. distance travelled during GNSS blackout")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "error_vs_distance.png", dpi=160)
    plt.close(fig)

    print(f"Saved plots to {out_dir}/")
    print("CNN checkpoints:", {k: v.get("drift_pct") for k, v in summary_cnn["checkpoints"].items()})
    print("GRU checkpoints:", {k: v.get("drift_pct") for k, v in summary_gru["checkpoints"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
