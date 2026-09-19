"""Tkinter digital-twin UI. Consumes DemoEngine; does not implement V2X fusion."""

from __future__ import annotations

import argparse
import math
import sys
import time
import tkinter as tk
from pathlib import Path

from .engine import DemoEngine
from .scenarios import SCENARIO_PRESETS, recording_spec
from .svg_export import write_svg

W, H = 1600, 900
MAP = (24, 72, 1080, 560)
PANEL = (1120, 72, 456, 560)
GRAPH = (24, 648, 1552, 150)

BG = "#090d16"
PANEL_BG = "#101624"
ROAD = "#262e3c"
LANE = "#c6d0dc"
EGO = "#3ddc97"
REMOTE = "#6e9eff"
BAD = "#e85d5d"
TRUTH = "#f4d35e"
BASE_C = "#e86e6e"
V2X_C = "#40d6c4"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
WARN = "#ffba49"
EDGE = "#2a3852"


class DemoApp:
    def __init__(self, engine: DemoEngine, root: tk.Tk):
        self.engine = engine
        self.root = root
        root.title("SIH26168 — Cooperative V2X Navigation (SIMULATION)")
        root.configure(bg=BG)
        root.geometry(f"{W}x{H}")
        root.resizable(False, False)
        self.canvas = tk.Canvas(root, width=W, height=H - 72, bg=BG, highlightthickness=0)
        self.canvas.pack(side=tk.TOP)
        bar = tk.Frame(root, bg="#0c121e", height=72)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        specs = [
            ("START / PAUSE", self._toggle),
            ("DEMO MODE", self._demo),
            ("GNSS OUTAGE", lambda: self.engine.trigger_gnss_outage()),
            ("INJECT BAD VEHICLE", lambda: self.engine.inject_bad_vehicle()),
            ("1 V2X", lambda: self.engine.set_remote_count(1)),
            ("3 V2X", lambda: self.engine.set_remote_count(3)),
            ("10 V2X", lambda: self.engine.set_remote_count(10)),
            ("RESET", self._reset),
        ]
        for lab, cmd in specs:
            b = tk.Button(
                bar,
                text=lab,
                command=cmd,
                bg="#182238",
                fg=TEXT,
                activebackground="#2a3d66",
                activeforeground=TEXT,
                relief=tk.FLAT,
                padx=10,
                pady=10,
                font=("DejaVu Sans", 9),
            )
            b.pack(side=tk.LEFT, padx=6, pady=12)
        tk.Label(
            bar,
            text="Space  start   G  outage   B  bad   D  demo   1/3/0 remotes   Esc  quit",
            bg="#0c121e",
            fg=MUTED,
            font=("DejaVu Sans", 8),
        ).pack(side=tk.LEFT, padx=12)
        root.bind("<space>", lambda _e: self._toggle())
        root.bind("g", lambda _e: self.engine.trigger_gnss_outage())
        root.bind("b", lambda _e: self.engine.inject_bad_vehicle())
        root.bind("d", lambda _e: self._demo())
        root.bind("r", lambda _e: self._reset())
        root.bind("1", lambda _e: self.engine.set_remote_count(1))
        root.bind("3", lambda _e: self.engine.set_remote_count(3))
        root.bind("0", lambda _e: self.engine.set_remote_count(10))
        root.bind("<Escape>", lambda _e: root.destroy())
        self._acc = 0.0
        self._last = time.perf_counter()
        self.ppm = 4.2
        self._tick()

    def _toggle(self) -> None:
        self.engine.paused = not self.engine.paused

    def _demo(self) -> None:
        self.engine.start_demo_mode()

    def _reset(self) -> None:
        self.engine.reset(self.engine.spec)
        self.engine.paused = True

    def _xy(self, east: float, north: float, cam_e: float, cam_n: float):
        x0, y0, w, h = MAP
        x = x0 + w / 2 + (east - cam_e) * self.ppm
        y = y0 + h * 0.72 - (north - cam_n) * self.ppm
        return x, y

    def _pill(self, x, y, w, h, fill, outline, text, tfill):
        c = self.canvas
        c.create_rectangle(x, y, x + w, y + h, fill=fill, outline=outline, width=2)
        c.create_text(x + w / 2, y + h / 2, fill=tfill, font=("DejaVu Sans", 12, "bold"), text=text)

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last
        self._last = now
        if not self.engine.paused:
            self._acc += dt
            step = self.engine.spec.dt_s
            while self._acc >= step and not self.engine.paused:
                self.engine.step()
                self._acc -= step
        self._draw(self.engine.snapshot())
        self.root.after(16, self._tick)

    def _draw(self, frame) -> None:
        c = self.canvas
        c.delete("all")
        cam_e, cam_n = frame.ego_truth_e, frame.ego_truth_n + 18.0
        x0, y0, w, h = MAP
        c.create_rectangle(0, 0, W, H, fill=BG, outline="")
        c.create_text(24, 22, anchor="w", fill=TEXT, font=("DejaVu Sans", 18, "bold"),
                      text="SIH26168  —  Cooperative V2X navigation")
        c.create_text(24, 44, anchor="w", fill=WARN, font=("DejaVu Sans", 9),
                      text="SIMULATION  ·  MODE A  ·  V2X RADIO: SIMULATED  ·  Toy filter — not Member 3")
        state = "PAUSED" if frame.paused else "RUNNING"
        c.create_text(W - 24, 22, anchor="e", fill=EGO if not frame.paused else MUTED,
                      font=("DejaVu Sans", 13, "bold"), text=state)
        if frame.caption:
            c.create_rectangle(430, 8, 1180, 52, fill="#162034", outline=EDGE)
            c.create_text(805, 30, fill=TEXT, font=("DejaVu Sans", 13, "bold"), text=frame.caption)

        c.create_rectangle(x0, y0, x0 + w, y0 + h, fill="#0c101a", outline=EDGE)
        lane_w = 3.7
        left = self._xy(-1.5 * lane_w, cam_n, cam_e, cam_n)[0]
        right = self._xy(1.5 * lane_w, cam_n, cam_e, cam_n)[0]
        c.create_rectangle(min(left, right), y0, max(left, right), y0 + h, fill=ROAD, outline="")
        dash_n0 = int((cam_n - 100) // 8) * 8
        for k in (-1, 0, 1):
            e = k * lane_w
            for n in range(dash_n0, dash_n0 + 240, 8):
                p0 = self._xy(e, n, cam_e, cam_n)
                p1 = self._xy(e, n + 4, cam_e, cam_n)
                col = "#f0f0f5" if k == 0 else LANE
                c.create_line(*p0, *p1, fill=col, width=2 if k else 3)
        for n0 in (0, 160, 320):
            ya = self._xy(0, n0 - 8, cam_e, cam_n)[1]
            yb = self._xy(0, n0 + 8, cam_e, cam_n)[1]
            c.create_rectangle(x0, min(ya, yb), x0 + w, max(ya, yb), fill="#303848", outline="")

        def path(pts, color, width):
            coords = []
            for e, n in pts[-400:]:
                coords.extend(self._xy(e, n, cam_e, cam_n))
            if len(coords) >= 4:
                c.create_line(*coords, fill=color, width=width, smooth=True)

        path(self.engine.truth_path, TRUTH, 2)
        path(self.engine.baseline_path, BASE_C, 2)
        path(self.engine.v2x_path, V2X_C, 3)

        you = next(v for v in frame.vehicles if v.is_ego)
        yx, yy = self._xy(you.east_m, you.north_m, cam_e, cam_n)
        show_nis = frame.fused_decision == "REJECT" or frame.bad_banner
        for lk in frame.links:
            rem = next((v for v in frame.vehicles if v.vehicle_id == lk.vehicle_id), None)
            if rem is None:
                continue
            rx, ry = self._xy(rem.east_m, rem.north_m, cam_e, cam_n)
            rejected = lk.gate == "REJECT"
            frac = max(0.0, min(1.0, lk.ttl / 0.9))
            width = 1.5 + 3.0 * frac
            col = BAD if rejected else (EGO if lk.gate == "ACCEPT" else WARN)
            c.create_line(rx, ry, yx, yy, fill=col, width=width)
            travel = 1.0 - frac
            mx = rx + (yx - rx) * travel
            my = ry + (yy - ry) * travel
            if rejected:
                hx, hy = (rx + yx) / 2, (ry + yy) / 2
                s = 6 + 4 * frac
                c.create_line(hx - s, hy - s, hx + s, hy + s, fill=BAD, width=3)
                c.create_line(hx - s, hy + s, hx + s, hy - s, fill=BAD, width=3)
            else:
                pr = 3.0 + 6.0 * frac
                c.create_oval(mx - pr, my - pr, mx + pr, my + pr, fill=col, outline="")

        bx, by = self._xy(frame.baseline_e, frame.baseline_n, cam_e, cam_n)
        vx, vy = self._xy(frame.v2x_e, frame.v2x_n, cam_e, cam_n)
        c.create_oval(bx - 5, by - 5, bx + 5, by + 5, outline=BASE_C, width=2)
        c.create_oval(vx - 6, vy - 6, vx + 6, vy + 6, outline=V2X_C, width=2)

        for v in frame.vehicles:
            cx, cy = self._xy(v.east_m, v.north_m, cam_e, cam_n)
            col = EGO if v.is_ego else (BAD if v.is_bad else REMOTE)
            L, Ww = (11, 6) if v.is_ego else (9, 5)
            hd = v.heading_rad
            ca, sa = math.cos(hd), math.sin(hd)
            pts = []
            for dx, dy in ((-Ww, -L), (Ww, -L), (Ww, L), (-Ww, L)):
                re = dx * ca - dy * sa
                rn = dx * sa + dy * ca
                pts.extend((cx + re, cy - rn))
            c.create_polygon(*pts, fill=col, outline="#ffffff")
            if v.is_ego:
                lab = "YOU"
            else:
                lab = f"{v.vehicle_id}  σpos {v.pos_std_m:.1f} m"
                if v.stale:
                    lab += "  STALE"
            c.create_text(cx + 16, cy - 14, anchor="w", fill=col, font=("DejaVu Sans", 8), text=lab)

        if frame.gnss_banner:
            c.create_rectangle(x0 + 180, y0 + 18, x0 + w - 180, y0 + 70, fill="#5a1a1a", outline=BAD, width=2)
            c.create_text(x0 + w / 2, y0 + 44, fill="#ffe8e8", font=("DejaVu Sans", 18, "bold"),
                          text="⚠  GNSS SIGNAL LOST")
        if frame.bad_banner:
            top = y0 + (88 if frame.gnss_banner else 18)
            c.create_rectangle(x0 + 160, top, x0 + w - 160, top + 48, fill="#4a2010", outline=WARN, width=2)
            c.create_text(x0 + w / 2, top + 24, fill=WARN, font=("DejaVu Sans", 16, "bold"),
                          text="⚠  UNRELIABLE V2X OBSERVATION")
        if show_nis:
            nis_val = frame.reject_nis if frame.reject_nis > 0.0 else frame.fused_nis
            c.create_rectangle(x0 + 16, y0 + 16, x0 + 300, y0 + 128, fill="#0c121e", outline=BAD, width=2)
            c.create_text(x0 + 28, y0 + 34, anchor="w", fill=BAD, font=("DejaVu Sans", 13, "bold"),
                          text="NIS GATE")
            vid = frame.reject_vehicle_id or "—"
            lines = [
                f"Vehicle: {vid}",
                f"Innovation NIS: {nis_val:.2f}",
                f"Decision: {frame.fused_decision}",
            ]
            yy = y0 + 56
            for line in lines:
                c.create_text(x0 + 28, yy, anchor="w", fill=TEXT, font=("DejaVu Sans", 10), text=line)
                yy += 20

        c.create_text(x0 + 16, y0 + h - 28, anchor="w", fill=TRUTH, font=("DejaVu Sans", 8), text="truth")
        c.create_text(x0 + 70, y0 + h - 28, anchor="w", fill=BASE_C, font=("DejaVu Sans", 8), text="baseline")
        c.create_text(x0 + 160, y0 + h - 28, anchor="w", fill=V2X_C, font=("DejaVu Sans", 8), text="V2X-assisted")
        c.create_text(x0 + 16, y0 + h - 12, anchor="w", fill=MUTED, font=("DejaVu Sans", 8),
                      text="V2X RADIO: SIMULATED    ·    Toy filter — not Member 3")

        px, py, pw, ph = PANEL
        c.create_rectangle(px, py, px + pw, py + ph, fill=PANEL_BG, outline=EDGE)
        c.create_text(px + 22, py + 22, anchor="w", fill=TEXT, font=("DejaVu Sans", 13, "bold"),
                      text="SYSTEM STATUS")
        gnss_ok = frame.gnss_available
        gnss_lab = "GNSS AVAILABLE" if gnss_ok else "GNSS DENIED"
        self._pill(px + 18, py + 40, pw - 36, 40,
                   "#163326" if gnss_ok else "#3a1518",
                   EGO if gnss_ok else BAD, gnss_lab, EGO if gnss_ok else BAD)
        vlab = f"V2X {frame.v2x_status}"
        vcol = EGO if frame.v2x_status == "ACTIVE" else (WARN if frame.v2x_status == "DEGRADED" else MUTED)
        vbg = "#163326" if frame.v2x_status == "ACTIVE" else ("#3a2a10" if frame.v2x_status == "DEGRADED" else "#1a2030")
        self._pill(px + 18, py + 88, pw - 36, 40, vbg, vcol, vlab, vcol)
        m = frame.meas_status
        if m == "MEASUREMENT ACCEPTED":
            mcol, mbg = EGO, "#163326"
        elif m == "DOWNWEIGHTED":
            mcol, mbg = WARN, "#3a2a10"
        elif m == "REJECTED":
            mcol, mbg = BAD, "#3a1518"
        else:
            mcol, mbg = MUTED, "#1a2030"
        self._pill(px + 18, py + 136, pw - 36, 40, mbg, mcol, m, mcol)
        c.create_text(px + 22, py + 192, anchor="w", fill=MUTED, font=("DejaVu Sans", 9),
                      text=f"Nearby cars: {frame.n_remotes}    ·    IMU ACTIVE")
        c.create_text(px + 22, py + 210, anchor="w", fill=WARN, font=("DejaVu Sans", 9),
                      text="V2X RADIO: SIMULATED")
        c.create_text(px + 22, py + 236, anchor="w", fill=MUTED, font=("DejaVu Sans", 10),
                      text="NAVIGATION ERROR (vs truth)")
        c.create_text(px + 22, py + 260, anchor="w", fill=BASE_C, font=("DejaVu Sans", 15, "bold"),
                      text=f"Baseline          {frame.baseline_err_m:6.2f} m")
        c.create_text(px + 22, py + 286, anchor="w", fill=V2X_C, font=("DejaVu Sans", 15, "bold"),
                      text=f"V2X-assisted   {frame.v2x_err_m:6.2f} m")
        hz = 1.0 / self.engine.spec.dt_s
        rows = [
            f"t = {frame.t:6.1f} s",
            f"Notes this step   {frame.messages_this_step}   ({frame.messages_this_step * hz:.0f}/s)",
            f"Received          {frame.received}",
            f"Accepted          {frame.accepted}",
            f"Downweighted      {frame.downweighted}",
            f"Rejected          {frame.rejected}",
            f"Decision          {frame.fused_decision}",
            f"Innovation NIS    {frame.fused_nis:.2f}",
            f"Meas. age         {frame.fused_age_s * 1000:.0f} ms",
        ]
        yy = py + 318
        for line in rows:
            c.create_text(px + 22, yy, anchor="w", fill=MUTED, font=("DejaVu Sans", 9), text=line)
            yy += 16
        if not frame.gnss_available:
            c.create_rectangle(px + 18, py + ph - 48, px + pw - 18, py + ph - 16, fill="#401c1c", outline="")
            c.create_text(px + pw / 2, py + ph - 32, fill=BAD, font=("DejaVu Sans", 12, "bold"),
                          text="GNSS SIGNAL LOST")

        if frame.show_endcard:
            c.create_rectangle(x0 + 80, y0 + 90, x0 + w - 80, y0 + h - 70, fill="#0e1624", outline=EDGE, width=2)
            c.create_text(x0 + w / 2, y0 + 120, fill=TEXT, font=("DejaVu Sans", 16, "bold"),
                          text="Final error  —  baseline vs V2X-assisted")
            c.create_text(x0 + 140, y0 + 170, anchor="w", fill=BASE_C, font=("DejaVu Sans", 18, "bold"),
                          text=f"Baseline                 {frame.baseline_err_m:.2f} m")
            c.create_text(x0 + 140, y0 + 210, anchor="w", fill=V2X_C, font=("DejaVu Sans", 18, "bold"),
                          text=f"V2X-assisted          {frame.v2x_err_m:.2f} m")
            c.create_text(x0 + 140, y0 + 270, anchor="w", fill=TEXT, font=("DejaVu Sans", 13),
                          text=f"Measurements received     {frame.received}")
            c.create_text(x0 + 140, y0 + 298, anchor="w", fill=EGO, font=("DejaVu Sans", 13),
                          text=f"Accepted                  {frame.accepted}")
            c.create_text(x0 + 140, y0 + 326, anchor="w", fill=WARN, font=("DejaVu Sans", 13),
                          text=f"Downweighted              {frame.downweighted}")
            c.create_text(x0 + 140, y0 + 354, anchor="w", fill=BAD, font=("DejaVu Sans", 13),
                          text=f"Rejected                  {frame.rejected}")
            c.create_text(x0 + w / 2, y0 + h - 90, fill=MUTED, font=("DejaVu Sans", 10),
                          text="Live filter errors  ·  Toy filter — not Member 3  ·  no claimed % gain")

        gx, gy, gw, gh = GRAPH
        c.create_rectangle(gx, gy, gx + gw, gy + gh, fill=PANEL_BG, outline=EDGE)
        c.create_text(gx + 16, gy + 14, anchor="w", fill=MUTED, font=("DejaVu Sans", 10),
                      text="Position error (m)  —  baseline vs V2X-assisted")
        c.create_text(gx + gw - 280, gy + 14, anchor="w", fill=BASE_C, font=("DejaVu Sans", 10), text="baseline")
        c.create_text(gx + gw - 160, gy + 14, anchor="w", fill=V2X_C, font=("DejaVu Sans", 10), text="V2X-assisted")
        inner = (gx + 70, gy + 28, gx + gw - 20, gy + gh - 14)
        c.create_rectangle(*inner, fill="#0a0e18", outline="")
        hist = frame.error_history
        span = 50.0
        if len(hist) >= 2:
            tmax = max(h[0] for h in hist)
            tmin = max(0.0, tmax - span)
            vis = [hh for hh in hist if hh[0] >= tmin]
            ymax = max(4.0, max(max(hh[1], hh[2]) for hh in vis) * 1.15)

            def gpt(t, err):
                x = inner[0] + (t - tmin) / span * (inner[2] - inner[0])
                y = inner[3] - (err / ymax) * (inner[3] - inner[1])
                return x, y

            outage = self.engine.spec.gnss_outage_s
            restore = self.engine.spec.gnss_restore_s
            if outage is None and self.engine.gnss_lost_at is not None:
                outage = self.engine.gnss_lost_at
            if outage is not None:
                t_den = max(tmin, outage)
                t_end = restore if restore is not None else tmax
                if restore is not None:
                    t_end = min(tmax, restore)
                xa = gpt(tmin, 0)[0]
                xb = gpt(min(max(tmin, outage), tmax), 0)[0]
                xc = gpt(min(max(t_den, t_end), tmax), 0)[0]
                xd = gpt(tmax, 0)[0]
                c.create_rectangle(xa, inner[1], xb, inner[3], fill="#10241c", outline="")
                c.create_rectangle(xb, inner[1], xc, inner[3], fill="#2a1218", outline="")
                if restore is not None and restore <= tmax:
                    c.create_rectangle(xc, inner[1], xd, inner[3], fill="#102430", outline="")
                if tmin <= outage <= tmax:
                    c.create_text(xb + 6, inner[1] + 8, anchor="w", fill=WARN, font=("DejaVu Sans", 8),
                                  text="GNSS DENIED")
                if tmin < outage:
                    c.create_text(xa + 6, inner[1] + 8, anchor="w", fill=EGO, font=("DejaVu Sans", 8),
                                  text="GNSS AVAILABLE")
                if restore is not None and tmin <= restore <= tmax:
                    c.create_text(xc + 6, inner[1] + 8, anchor="w", fill=V2X_C, font=("DejaVu Sans", 8),
                                  text="GNSS RESTORED")
            for idx, col in ((1, BASE_C), (2, V2X_C)):
                coords = []
                for hh in vis:
                    coords.extend(gpt(hh[0], hh[idx]))
                if len(coords) >= 4:
                    c.create_line(*coords, fill=col, width=2)
            c.create_text(gx + 12, inner[1], anchor="w", fill=MUTED, font=("DejaVu Sans", 8), text=f"{ymax:.0f}")
            c.create_text(gx + 28, inner[3] - 4, anchor="w", fill=MUTED, font=("DejaVu Sans", 8), text="0")


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SIH26168 Mode-A V2X digital twin (SIMULATION)")
    p.add_argument("--scenario", default="recording", choices=sorted(SCENARIO_PRESETS))
    p.add_argument("--demo", action="store_true")
    p.add_argument("--screenshot", type=str, default="")
    p.add_argument("--until", type=float, default=21.0)
    p.add_argument("--headless", action="store_true")
    args = p.parse_args(argv)
    spec = recording_spec() if args.demo else SCENARIO_PRESETS[args.scenario]
    engine = DemoEngine(spec)
    if args.demo or args.screenshot:
        engine.paused = False

    if args.screenshot:
        engine.paused = False
        while engine.t + 1e-9 < args.until and not (engine.paused and engine.t > 0):
            engine.step()
            if engine.t >= spec.duration_s:
                break
        path = Path(args.screenshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_svg(path.with_suffix(".svg") if path.suffix.lower() != ".svg" else path, engine)
        # keep requested name; if png requested also write svg beside it
        if path.suffix.lower() == ".png":
            svg = path.with_suffix(".svg")
            write_svg(svg, engine)
            print(f"wrote {svg} at t={engine.snapshot().t:.1f}s (PNG skipped: no pygame/SDL)")
        else:
            print(f"wrote {path} at t={engine.snapshot().t:.1f}s")
        return 0

    if args.headless:
        print("headless requires --screenshot", file=sys.stderr)
        return 2

    root = tk.Tk()
    DemoApp(engine, root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
