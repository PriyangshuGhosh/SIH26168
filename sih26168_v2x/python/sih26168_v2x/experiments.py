"""SIMULATION experiments. Not Member 3. Not Android. Not real V2X."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .core import V2XCore
from .frames import local_enu_to_geo
from .simulator import RemoteTruth, SimConfig, V2XSimulator
from .types import EnuOrigin, EnuVector, GeoPosition, LocalNavigationState, V2XConfig


@dataclass
class Metrics:
    pos_rmse_m: float
    vel_rmse_mps: float
    heading_err_rad: float
    p95_pos_m: float
    drift_outage_m: float
    recovery_m: float
    n: int


def _rmse(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    return math.sqrt(sum(x * x for x in xs) / len(xs))


def _p95(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    return ys[min(len(ys) - 1, int(0.95 * len(ys)))]


class ToyEKF:
    """4-state [n,e,vn,ve] toy filter for SIMULATION comparisons only."""

    def __init__(self):
        self.n = 0.0
        self.e = 0.0
        self.vn = 16.0
        self.ve = 0.0
        self.pn = 25.0
        self.pe = 25.0

    def predict(self, dt: float, imu_an: float, imu_ae: float) -> None:
        self.n += self.vn * dt
        self.e += self.ve * dt
        self.vn += imu_an * dt
        self.ve += imu_ae * dt
        self.pn += 4.0 * dt
        self.pe += 4.0 * dt

    def update_speed(self, speed: float, var: float) -> None:
        sp = math.hypot(self.vn, self.ve)
        if sp < 1e-9:
            self.vn = speed
            return
        scale = speed / sp
        self.vn *= scale
        self.ve *= scale
        self.pn = min(self.pn, self.pn * 0.98 + var)

    def update_gnss(self, n: float, e: float, var: float) -> None:
        kn = self.pn / (self.pn + var)
        ke = self.pe / (self.pe + var)
        self.n += kn * (n - self.n)
        self.e += ke * (e - self.e)
        self.pn *= (1 - kn)
        self.pe *= (1 - ke)

    def update_v2x(self, n: float, e: float, var: float, gated: bool, nis: float) -> None:
        if gated and nis > 9.210:
            return
        scale = 4.0 if (gated and nis > 5.991) else 1.0
        self.update_gnss(n, e, var * scale)


def run_blackout(n_remotes: int, mode: str, seed: int = 3, dt: float = 0.2) -> Metrics:
    """0-60 GNSS, 60-180 denied, 180-240 GNSS. SIMULATION."""
    origin = EnuOrigin(12.9716, 77.5946, 920.0, True)
    remotes = [RemoteTruth(f"r{i}", 0.0, 16.0, 0.0, 20.0 + 8 * i, 0.5 * i, pos_std_m=2.5) for i in range(n_remotes)]
    sim = V2XSimulator(SimConfig(seed=seed, remotes=remotes, dt_s=dt))
    core = V2XCore(V2XConfig(origin_locked=True))
    core.lock_origin(origin)
    ekf = ToyEKF()
    rng = sim.rng
    pos_err = []
    vel_err = []
    head_err = []
    outage_err = []
    recover_err = []
    t = 0.0
    while t <= 240.0 + 1e-9:
        gnss = t < 60.0 or t >= 180.0
        # Ego truth: northing at 16 m/s.
        n_true = 16.0 * t
        e_true = 0.0
        imu_an = rng.gauss(0.0, 0.35)
        imu_ae = rng.gauss(0.0, 0.35)
        ekf.predict(dt, imu_an, imu_ae)
        if mode != "imu" and abs(math.hypot(ekf.vn, ekf.ve) - 16.0) < 50:
            ekf.update_speed(16.0 + rng.gauss(0.0, 0.3), 0.2)
        geo_est = local_enu_to_geo(EnuVector(ekf.e, ekf.n, 0.0), origin)
        local = LocalNavigationState(
            timestamp_s=t,
            latitude_deg=geo_est.latitude_deg,
            longitude_deg=geo_est.longitude_deg,
            altitude_m=920.0,
            v_x=math.hypot(ekf.vn, ekf.ve),
            v_y=0.0,
            yaw_rad=0.0,
            position_cov_ne=[[ekf.pn, 0.0], [0.0, ekf.pe]],
            gnss_available=gnss,
            valid=True,
        )
        if gnss:
            ekf.update_gnss(n_true + rng.gauss(0.0, 1.5), e_true + rng.gauss(0.0, 1.5), 4.0)
            geo_est = local_enu_to_geo(EnuVector(ekf.e, ekf.n, 0.0), origin)
            local.latitude_deg = geo_est.latitude_deg
            local.longitude_deg = geo_est.longitude_deg
            local.position_cov_ne = [[ekf.pn, 0.0], [0.0, ekf.pe]]
        if n_remotes and mode in ("v2x_ungated", "v2x_gated"):
            for m in sim.messages_at(t):
                core.ingest(m)
            r = core.get_cooperative_measurement(local)
            if r.measurement and r.measurement.has_position:
                var = r.measurement.position_cov_ne[0][0]
                if mode == "v2x_ungated":
                    ekf.update_gnss(r.measurement.north_m, r.measurement.east_m, var)
                else:
                    ekf.update_v2x(r.measurement.north_m, r.measurement.east_m, var, True, r.nis)
        pe = math.hypot(ekf.n - n_true, ekf.e - e_true)
        ve = abs(math.hypot(ekf.vn, ekf.ve) - 16.0)
        he = abs(math.atan2(ekf.ve, ekf.vn))
        pos_err.append(pe)
        vel_err.append(ve)
        head_err.append(he)
        if 60.0 <= t <= 180.0:
            outage_err.append(pe)
        if t >= 180.0:
            recover_err.append(pe)
        t += dt
    return Metrics(_rmse(pos_err), _rmse(vel_err), _rmse(head_err), _p95(pos_err),
                   outage_err[-1] if outage_err else float("nan"),
                   recover_err[-1] if recover_err else float("nan"), len(pos_err))


def run_suite() -> dict:
    out = {}
    for n in (0, 1, 3, 10):
        for mode in ("imu", "imu_ai", "v2x_ungated", "v2x_gated"):
            m = mode if mode != "imu_ai" else "ai"
            key_mode = "imu" if mode == "imu" else ("ai" if mode == "imu_ai" else mode)
            if mode == "imu_ai":
                key_mode = "ai"
                metrics = run_blackout(n, "ai")
            elif mode == "imu":
                metrics = run_blackout(n, "imu")
            else:
                metrics = run_blackout(n, mode)
            out[f"n{n}_{key_mode}"] = metrics
    return out


if __name__ == "__main__":
    for k, v in run_suite().items():
        print(f"{k}: pos_rmse={v.pos_rmse_m:.2f} m  outage_end={v.drift_outage_m:.2f} m  "
              f"p95={v.p95_pos_m:.2f} recovery={v.recovery_m:.2f}")
    print("LABEL: SIMULATION. Not real V2X. Not Member 3. Not Android.")
