"""SVG still-frame export from DemoEngine (no extra GUI deps)."""

from __future__ import annotations

import html
from pathlib import Path

from .engine import DemoEngine


def write_svg(path: Path, engine: DemoEngine) -> None:
    frame = engine.snapshot()
    w, h = 1600, 820
    mx, my, mw, mh = 24, 64, 1080, 520
    ppm = 4.2
    cam_e, cam_n = frame.ego_truth_e, frame.ego_truth_n + 18.0

    def xy(e, n):
        return mx + mw / 2 + (e - cam_e) * ppm, my + mh * 0.72 - (n - cam_n) * ppm

    def poly(pts, color, width=2):
        if len(pts) < 2:
            return ""
        d = " ".join(f"{xy(e, n)[0]:.1f},{xy(e, n)[1]:.1f}" for e, n in pts[-400:])
        return f'<polyline fill="none" stroke="{color}" stroke-width="{width}" points="{d}"/>'

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#090d16"/>',
        '<text x="24" y="28" fill="#e2e8f0" font-family="DejaVu Sans, sans-serif" font-size="22" font-weight="700">'
        "SIH26168 — Cooperative V2X navigation</text>",
        '<text x="24" y="48" fill="#ffba49" font-family="DejaVu Sans, sans-serif" font-size="12">'
        "SIMULATION · MODE A · V2X RADIO: SIMULATED · Toy filter — not Member 3</text>",
        f'<rect x="{mx}" y="{my}" width="{mw}" height="{mh}" fill="#0c101a" stroke="#2a3852"/>',
        f'<rect x="1120" y="{my}" width="456" height="{mh}" fill="#101624" stroke="#2a3852"/>',
        '<text x="1144" y="86" fill="#e2e8f0" font-family="DejaVu Sans, sans-serif" font-size="16" font-weight="700">'
        "SYSTEM STATUS</text>",
    ]
    if frame.caption:
        parts.append(
            f'<text x="800" y="36" text-anchor="middle" fill="#e2e8f0" font-family="DejaVu Sans, sans-serif" '
            f'font-size="14">{html.escape(frame.caption)}</text>'
        )
    parts.append(poly(engine.truth_path, "#f4d35e", 2))
    parts.append(poly(engine.baseline_path, "#e86e6e", 2))
    parts.append(poly(engine.v2x_path, "#40d6c4", 3))
    you = next(v for v in frame.vehicles if v.is_ego)
    yx, yy = xy(you.east_m, you.north_m)
    for lk in frame.links:
        rem = next((v for v in frame.vehicles if v.vehicle_id == lk.vehicle_id), None)
        if rem is None:
            continue
        rx, ry = xy(rem.east_m, rem.north_m)
        rejected = lk.gate == "REJECT"
        col = "#e85d5d" if rejected else "#3ddc97"
        frac = max(0.0, min(1.0, lk.ttl / 0.9))
        sw = 1.5 + 3.0 * frac
        parts.append(
            f'<line x1="{rx:.1f}" y1="{ry:.1f}" x2="{yx:.1f}" y2="{yy:.1f}" '
            f'stroke="{col}" stroke-width="{sw:.1f}"/>'
        )
        if rejected:
            hx, hy = (rx + yx) / 2, (ry + yy) / 2
            parts.append(
                f'<line x1="{hx - 8:.1f}" y1="{hy - 8:.1f}" x2="{hx + 8:.1f}" y2="{hy + 8:.1f}" '
                f'stroke="#e85d5d" stroke-width="3"/>'
            )
            parts.append(
                f'<line x1="{hx - 8:.1f}" y1="{hy + 8:.1f}" x2="{hx + 8:.1f}" y2="{hy - 8:.1f}" '
                f'stroke="#e85d5d" stroke-width="3"/>'
            )
    for v in frame.vehicles:
        cx, cy = xy(v.east_m, v.north_m)
        col = "#3ddc97" if v.is_ego else ("#e85d5d" if v.is_bad else "#6e9eff")
        r = 9 if v.is_ego else 7
        parts.append(
            f'<rect x="{cx - r}" y="{cy - r * 1.4}" width="{2 * r}" height="{2.8 * r}" fill="{col}" '
            f'stroke="#fff"/>'
        )
        if v.is_ego:
            lab = "YOU"
        else:
            lab = f"{v.vehicle_id} σpos {v.pos_std_m:.1f} m"
            if v.stale:
                lab += " STALE"
        parts.append(
            f'<text x="{cx + 12}" y="{cy - 10}" fill="{col}" font-size="11" '
            f'font-family="DejaVu Sans, sans-serif">{html.escape(lab)}</text>'
        )
    gnss = "GNSS AVAILABLE" if frame.gnss_available else "GNSS DENIED"
    gcol = "#3ddc97" if frame.gnss_available else "#e85d5d"
    vcol = "#3ddc97" if frame.v2x_status == "ACTIVE" else (
        "#ffba49" if frame.v2x_status == "DEGRADED" else "#94a3b8"
    )
    m = frame.meas_status
    if m == "MEASUREMENT ACCEPTED":
        mcol = "#3ddc97"
    elif m in ("DOWNWEIGHTED",):
        mcol = "#ffba49"
    elif m == "REJECTED":
        mcol = "#e85d5d"
    else:
        mcol = "#94a3b8"
    panel = [
        (gnss, gcol),
        (f"V2X {frame.v2x_status}  ({frame.n_remotes} nearby)", vcol),
        (m, mcol),
        ("V2X RADIO: SIMULATED", "#ffba49"),
        (f"Baseline {frame.baseline_err_m:.2f} m", "#e86e6e"),
        (f"V2X-assisted {frame.v2x_err_m:.2f} m", "#40d6c4"),
        (f"t={frame.t:.1f}s  received {frame.received}", "#94a3b8"),
        (f"ACCEPT {frame.accepted}  DOWNWEIGHT {frame.downweighted}  REJECT {frame.rejected}", "#94a3b8"),
        (f"Innovation NIS {frame.fused_nis:.2f}  {frame.fused_decision}", "#e2e8f0"),
        ("Toy filter — not Member 3", "#94a3b8"),
    ]
    py = my + 48
    for line, fill in panel:
        parts.append(
            f'<text x="1144" y="{py}" fill="{fill}" font-size="14" '
            f'font-family="DejaVu Sans, sans-serif">{html.escape(line)}</text>'
        )
        py += 24
    if not frame.gnss_available:
        parts.append(
            f'<text x="1144" y="{my + mh - 24}" fill="#e85d5d" font-size="16" font-weight="700" '
            f'font-family="DejaVu Sans, sans-serif">GNSS SIGNAL LOST</text>'
        )
        if frame.gnss_banner:
            parts.append(
                f'<rect x="{mx + 200}" y="{my + 16}" width="{mw - 400}" height="44" '
                f'fill="#5a1a1a" stroke="#e85d5d"/>'
            )
            parts.append(
                f'<text x="{mx + mw / 2:.0f}" y="{my + 44}" text-anchor="middle" fill="#ffe8e8" '
                f'font-size="20" font-weight="700" font-family="DejaVu Sans, sans-serif">'
                "GNSS SIGNAL LOST</text>"
            )
    if frame.fused_decision == "REJECT" or frame.bad_banner:
        nis_val = frame.reject_nis if frame.reject_nis > 0.0 else frame.fused_nis
        vid = frame.reject_vehicle_id or "—"
        parts.append(
            f'<rect x="{mx + 16}" y="{my + 16}" width="280" height="90" fill="#0c121e" stroke="#e85d5d"/>'
        )
        parts.append(
            f'<text x="{mx + 28}" y="{my + 38}" fill="#e85d5d" font-size="14" font-weight="700" '
            f'font-family="DejaVu Sans, sans-serif">NIS GATE</text>'
        )
        parts.append(
            f'<text x="{mx + 28}" y="{my + 58}" fill="#e2e8f0" font-size="12" '
            f'font-family="DejaVu Sans, sans-serif">{html.escape(f"Vehicle: {vid}")}</text>'
        )
        parts.append(
            f'<text x="{mx + 28}" y="{my + 76}" fill="#e2e8f0" font-size="12" '
            f'font-family="DejaVu Sans, sans-serif">'
            f"{html.escape(f'Innovation NIS: {nis_val:.2f}')}</text>"
        )
        parts.append(
            f'<text x="{mx + 28}" y="{my + 94}" fill="#e2e8f0" font-size="12" '
            f'font-family="DejaVu Sans, sans-serif">'
            f"{html.escape(f'Decision: {frame.fused_decision}')}</text>"
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")
