"""Static PNG plots for baseline results (matplotlib, Agg backend)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_MUTED = "#52514e"
GRID = "#e4e3de"
# Fixed categorical order: colour follows the model, never its rank.
MODEL_COLORS = {
    "constant_mean": "#2a78d6",
    "ridge_features": "#eb6834",
    "ridge_features_so3aug": "#1baf7a",
    "physics_integration": "#eda100",
    "cnn": "#e87ba4",
    "tcn": "#008300",
}


def _style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(ncols: int, width: float, height: float) -> tuple[plt.Figure, np.ndarray]:
    fig, axes = plt.subplots(1, ncols, figsize=(width, height), squeeze=False, facecolor=SURFACE)
    return fig, axes[0]


def plot_mae_overview(results: dict[str, Any], out: Path) -> None:
    windows = list(results["metrics"])
    fig, axes = _figure(len(windows), 5.5 * len(windows), 4.0)
    for ax, w in zip(axes, windows):
        models = list(results["metrics"][w])
        splits = ("val", "test")
        width = 0.8 / len(models)
        for i, m in enumerate(models):
            vals = [results["metrics"][w][m][s]["overall"]["mae_mps"] for s in splits]
            x = np.arange(len(splits)) + (i - (len(models) - 1) / 2) * width
            ax.bar(x, vals, width * 0.92, color=MODEL_COLORS.get(m), label=m)
        ax.set_xticks(range(len(splits)), ["validation (M)", "test (S)"], color=TEXT)
        ax.set_title(f"window = {w} samples", color=TEXT, fontsize=11, loc="left")
        ax.set_ylabel("MAE (m/s)", color=TEXT_MUTED)
        _style(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, labelcolor=TEXT, ncols=len(labels), loc="lower center")
    fig.suptitle("Baseline MAE by split", color=TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_speed_bins(results: dict[str, Any], window: str, out: Path) -> None:
    metrics = results["metrics"][window]
    models = list(metrics)
    bins = list(metrics[models[0]]["test"]["by_speed_bin_mps"])
    fig, axes = _figure(1, 9.0, 4.0)
    ax = axes[0]
    width = 0.8 / len(models)
    for i, m in enumerate(models):
        vals = [metrics[m]["test"]["by_speed_bin_mps"].get(b, {}).get("mae_mps", np.nan) for b in bins]
        x = np.arange(len(bins)) + (i - (len(models) - 1) / 2) * width
        ax.bar(x, vals, width * 0.92, color=MODEL_COLORS.get(m), label=m)
    ax.set_xticks(range(len(bins)), bins, color=TEXT)
    ax.set_xlabel("true speed bin (m/s)", color=TEXT_MUTED)
    ax.set_ylabel("MAE (m/s)", color=TEXT_MUTED)
    ax.set_title(f"Test (S series) MAE per speed bin, window = {window} samples", color=TEXT, fontsize=11, loc="left")
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper center")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_test_timeseries(plot_data: dict[str, Any], window: str, out: Path, max_seconds: float = 900.0) -> None:
    d = plot_data[window]
    sessions, counts = np.unique(d["test_session_id"], return_counts=True)
    session = sessions[np.argmax(counts)]
    m = d["test_session_id"] == session
    t = d["test_t_s"][m]
    keep = t <= t[0] + max_seconds
    fig, axes = _figure(1, 11.0, 4.0)
    ax = axes[0]
    ax.plot(t[keep], d["test_true"][m][keep], color=TEXT, linewidth=2.0, label="ground truth")
    for name in ("ridge_features_so3aug", "ridge_features", "physics_integration"):
        if name in d["test_pred"]:
            ax.plot(t[keep], d["test_pred"][name][m][keep], color=MODEL_COLORS[name], linewidth=1.2, label=name)
    ax.set_xlabel("session time (s)", color=TEXT_MUTED)
    ax.set_ylabel("speed (m/s)", color=TEXT_MUTED)
    ax.set_title(f"Test session {session}: first {max_seconds:g} s, window = {window} samples", color=TEXT, fontsize=11, loc="left")
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, ncols=4, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_baselines(results: dict[str, Any], plot_data: dict[str, Any], out_dir: Path) -> None:
    plot_mae_overview(results, out_dir / "mae_overview.png")
    for w in results["metrics"]:
        plot_speed_bins(results, w, out_dir / f"test_mae_by_speed_bin_w{w}.png")
        plot_test_timeseries(plot_data, w, out_dir / f"test_timeseries_w{w}.png")


# ----------------------------------------------------------------------------- neural models (Milestone 2)


def plot_training_curves(history: list[dict[str, Any]], title: str, out: Path) -> None:
    """Training loss and validation MAE per epoch as two panels (different units, no shared axis)."""
    epochs = [h["epoch"] for h in history]
    best = min(history, key=lambda h: h["val_mae_mps"])
    fig, axes = _figure(2, 11.0, 3.6)
    axes[0].plot(epochs, [h["train_loss"] for h in history], color=MODEL_COLORS["constant_mean"], linewidth=2.0)
    axes[0].set_ylabel("training loss (Huber, m/s)", color=TEXT_MUTED)
    axes[1].plot(epochs, [h["val_mae_mps"] for h in history], color=MODEL_COLORS["ridge_features"], linewidth=2.0)
    axes[1].plot([best["epoch"]], [best["val_mae_mps"]], "o", color=MODEL_COLORS["ridge_features"], markersize=8,
                 markeredgecolor=SURFACE, markeredgewidth=2)
    axes[1].annotate(f"best {best['val_mae_mps']:.2f} m/s @ {best['epoch']}", (best["epoch"], best["val_mae_mps"]),
                     textcoords="offset points", xytext=(6, 8), color=TEXT, fontsize=9)
    axes[1].set_ylabel("validation MAE (m/s)", color=TEXT_MUTED)
    for ax in axes:
        ax.set_xlabel("epoch", color=TEXT_MUTED)
        _style(ax)
    fig.suptitle(title, color=TEXT, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_model_comparison(metrics: dict[str, dict[str, Any]], models: list[str], out: Path) -> None:
    """Grouped MAE bars per window for val and test. ``metrics[window][model][split]["overall"]``."""
    windows = list(metrics)
    fig, axes = _figure(len(windows), 5.8 * len(windows), 4.0)
    for ax, w in zip(axes, windows):
        present = [m for m in models if m in metrics[w]]
        width = 0.8 / len(present)
        for i, m in enumerate(present):
            vals = [metrics[w][m][s]["overall"]["mae_mps"] for s in ("val", "test")]
            x = np.arange(2) + (i - (len(present) - 1) / 2) * width
            ax.bar(x, vals, width * 0.92, color=MODEL_COLORS.get(m), label=m)
        ax.set_xticks(range(2), ["validation (M)", "test (S)"], color=TEXT)
        ax.set_title(f"window = {w} samples", color=TEXT, fontsize=11, loc="left")
        ax.set_ylabel("MAE (m/s)", color=TEXT_MUTED)
        _style(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, labelcolor=TEXT, ncols=len(labels), loc="lower center")
    fig.suptitle("Neural models vs baselines: MAE", color=TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_breakdown_comparison(split_metrics: dict[str, dict[str, Any]], key: str, title: str, xlabel: str, out: Path) -> None:
    """MAE per category (``key`` = "by_speed_bin_mps", "by_trip" or "stationary_vs_moving") for several models."""
    models = list(split_metrics)
    cats = list(split_metrics[models[0]][key])
    fig, axes = _figure(1, max(7.0, 1.2 * len(cats) + 2), 4.0)
    ax = axes[0]
    width = 0.8 / len(models)
    for i, m in enumerate(models):
        vals = [split_metrics[m][key].get(c, {}).get("mae_mps", np.nan) for c in cats]
        x = np.arange(len(cats)) + (i - (len(models) - 1) / 2) * width
        ax.bar(x, vals, width * 0.92, color=MODEL_COLORS.get(m.split(" ")[0]), label=m)
    ax.set_xticks(range(len(cats)), cats, color=TEXT)
    ax.set_xlabel(xlabel, color=TEXT_MUTED)
    ax.set_ylabel("MAE (m/s)", color=TEXT_MUTED)
    ax.set_title(title, color=TEXT, fontsize=11, loc="left")
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper center", ncols=len(models))
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_prediction_timeseries(session_id: np.ndarray, t_s: np.ndarray, y_true: np.ndarray, preds: dict[str, np.ndarray],
                               title: str, out: Path, session: str | None = None, max_seconds: float = 900.0) -> None:
    """Ground truth vs predictions for one session (default: the one with most windows)."""
    if session is None:
        sessions, counts = np.unique(session_id, return_counts=True)
        session = sessions[np.argmax(counts)]
    m = session_id == session
    t = t_s[m]
    keep = t <= t[0] + max_seconds
    fig, axes = _figure(1, 11.0, 4.0)
    ax = axes[0]
    ax.plot(t[keep], y_true[m][keep], color=TEXT, linewidth=2.0, label="ground truth")
    for name, p in preds.items():
        ax.plot(t[keep], p[m][keep], color=MODEL_COLORS.get(name), linewidth=1.2, label=name)
    ax.set_xlabel("session time (s)", color=TEXT_MUTED)
    ax.set_ylabel("speed (m/s)", color=TEXT_MUTED)
    ax.set_title(f"{title}: session {session}, first {max_seconds:g} s", color=TEXT, fontsize=11, loc="left")
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, ncols=len(preds) + 1, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


# ----------------------------------------------------------------------------- uncertainty (Milestone 3)


def plot_calibration_curve(uncertainty_report: dict[str, Any], title: str, out: Path, color: str | None = None) -> None:
    """Reliability diagram: expected vs observed coverage per nominal confidence level, plus the
    perfect-calibration diagonal. Points above the diagonal are underconfident (sigma too large);
    points below are overconfident (sigma too small). ``color`` should identify the model shown
    (e.g. ``MODEL_COLORS[arch]``) -- it defaults to the CNN colour only as a last resort."""
    color = color or MODEL_COLORS["cnn"]
    levels = uncertainty_report["levels"]
    expected = [d["expected_coverage"] for d in levels.values()]
    observed = [d["observed_coverage"] for d in levels.values()]
    fig, axes = _figure(1, 5.5, 5.0)
    ax = axes[0]
    ax.plot([0, 1], [0, 1], color=GRID, linewidth=1.5, linestyle="--", label="perfect calibration")
    ax.plot(expected, observed, "o-", color=color, linewidth=2.0, markersize=7, label="observed")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("nominal (expected) coverage", color=TEXT_MUTED)
    ax.set_ylabel("observed coverage", color=TEXT_MUTED)
    ax.set_title(title, color=TEXT, fontsize=11, loc="left")
    ax.text(0.02, 0.95, f"NLL={uncertainty_report['nll']:.3f}  mean sigma={uncertainty_report['mean_sigma_mps']:.2f} m/s",
            transform=ax.transAxes, fontsize=9, color=TEXT_MUTED, va="top")
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_robustness(robustness_report: dict[str, dict[str, Any]], title: str, out: Path, color: str | None = None) -> None:
    """MAE under each perturbation vs the clean baseline, for one model. ``color`` should identify
    the model shown (e.g. ``MODEL_COLORS[arch]``) -- it defaults to the CNN colour as a last resort."""
    color = color or MODEL_COLORS["cnn"]
    names = [n for n in robustness_report if n != "clean"]
    clean_mae = robustness_report["clean"]["regression"]["mae_mps"]
    vals = [robustness_report[n]["regression"]["mae_mps"] for n in names]
    fig, axes = _figure(1, max(7.0, 1.3 * len(names) + 2), 4.0)
    ax = axes[0]
    ax.axhline(clean_mae, color=TEXT_MUTED, linewidth=1.2, linestyle="--", label=f"clean ({clean_mae:.2f} m/s)")
    ax.bar(range(len(names)), vals, 0.6, color=color)
    ax.set_xticks(range(len(names)), names, color=TEXT, rotation=20, ha="right")
    ax.set_ylabel("MAE (m/s)", color=TEXT_MUTED)
    ax.set_title(title, color=TEXT, fontsize=11, loc="left")
    _style(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_selection_matrix(candidates: dict[str, dict[str, Any]], selected_key: str, out: Path) -> None:
    """Validation MAE and parameter count for every (arch, window) candidate in the selection matrix."""
    keys = list(candidates)
    fig, axes = _figure(2, 10.0, 4.0)
    mae = [candidates[k]["metrics"]["val"]["overall"]["mae_mps"] for k in keys]
    params = [candidates[k]["info"]["n_parameters"] for k in keys]
    colors = [MODEL_COLORS.get(candidates[k]["arch"]) for k in keys]
    edge = ["#0b0b0b" if k == selected_key else "none" for k in keys]
    axes[0].bar(range(len(keys)), mae, 0.6, color=colors, edgecolor=edge, linewidth=2.0)
    axes[0].set_xticks(range(len(keys)), keys, color=TEXT, rotation=20, ha="right")
    axes[0].set_ylabel("validation MAE (m/s)", color=TEXT_MUTED)
    axes[0].set_title("Selection matrix: accuracy", color=TEXT, fontsize=11, loc="left")
    axes[1].bar(range(len(keys)), params, 0.6, color=colors, edgecolor=edge, linewidth=2.0)
    axes[1].set_xticks(range(len(keys)), keys, color=TEXT, rotation=20, ha="right")
    axes[1].set_ylabel("parameters", color=TEXT_MUTED)
    axes[1].set_title("Selection matrix: model size (selected outlined)", color=TEXT, fontsize=11, loc="left")
    for ax in axes:
        _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)
