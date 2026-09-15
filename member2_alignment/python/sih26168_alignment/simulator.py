"""Deterministic synthetic IMU generator for Member 2 validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .frames import rotation_zyx, vehicleToPhoneVector

SEED = 26168
G = 9.80665


@dataclass
class ScenarioTruth:
    name: str
    t: np.ndarray
    acc_p: np.ndarray
    gyro_p: np.ndarray
    acc_v: np.ndarray
    gyro_v: np.ndarray
    R_vp: np.ndarray
    q_pv: np.ndarray
    gnss_speed: np.ndarray | None
    gnss_hdop: np.ndarray | None
    gnss_sats: np.ndarray | None
    notes: str


def _quat_from_R(R: np.ndarray) -> np.ndarray:
    from .frames import quat_from_rotation_matrix

    return quat_from_rotation_matrix(R)


def _time(duration_s: float, hz: float = 100.0) -> np.ndarray:
    n = int(round(duration_s * hz))
    return np.arange(n, dtype=float) / hz


def _stationary_vehicle(n: int) -> tuple[np.ndarray, np.ndarray]:
    acc = np.zeros((n, 3))
    acc[:, 2] = G
    gyro = np.zeros((n, 3))
    return acc, gyro


def generate_scenario(name: str, rng: np.random.Generator | None = None) -> ScenarioTruth:
    rng = rng or np.random.default_rng(SEED)
    hz = 100.0
    makers: dict[str, Callable[[np.random.Generator], ScenarioTruth]] = {
        "stationary_phone": _sc_stationary,
        "arbitrary_mount": _sc_arbitrary_mount,
        "straight_acceleration": _sc_straight_accel,
        "braking": _sc_braking,
        "turning": _sc_turning,
        "pothole": _sc_pothole,
        "vibration": _sc_vibration,
        "phone_movement": _sc_phone_movement,
        "weak_acceleration": _sc_weak_accel,
        "gnss_assisted": _sc_gnss_assisted,
        "noisy_imu": _sc_noisy,
        "gyro_bias": _sc_gyro_bias,
        "accel_bias": _sc_accel_bias,
        "motion_dropout": _sc_motion_dropout,
    }
    if name not in makers:
        raise KeyError(f"unknown scenario {name}")
    return makers[name](rng)


def all_scenario_names() -> list[str]:
    return [
        "stationary_phone",
        "arbitrary_mount",
        "straight_acceleration",
        "braking",
        "turning",
        "pothole",
        "vibration",
        "phone_movement",
        "weak_acceleration",
        "gnss_assisted",
        "noisy_imu",
        "gyro_bias",
        "accel_bias",
        "motion_dropout",
    ]


def _pack(
    name: str,
    t: np.ndarray,
    acc_v: np.ndarray,
    gyro_v: np.ndarray,
    R_vp: np.ndarray,
    notes: str,
    noise_acc: float = 0.0,
    noise_gyro: float = 0.0,
    acc_bias_p: np.ndarray | None = None,
    gyro_bias_p: np.ndarray | None = None,
    rng: np.random.Generator | None = None,
    gnss_speed: np.ndarray | None = None,
    R_series: np.ndarray | None = None,
) -> ScenarioTruth:
    n = t.shape[0]
    acc_p = np.zeros_like(acc_v)
    gyro_p = np.zeros_like(gyro_v)
    q = np.zeros((n, 4))
    if R_series is None:
        R_use = np.repeat(R_vp[None, ...], n, axis=0)
    else:
        R_use = R_series
        R_vp = R_series[0]
    for i in range(n):
        acc_p[i] = vehicleToPhoneVector(R_use[i], acc_v[i])
        gyro_p[i] = vehicleToPhoneVector(R_use[i], gyro_v[i])
        q[i] = _quat_from_R(R_use[i])
    rng = rng or np.random.default_rng(SEED)
    if noise_acc > 0:
        acc_p = acc_p + rng.normal(0.0, noise_acc, size=acc_p.shape)
    if noise_gyro > 0:
        gyro_p = gyro_p + rng.normal(0.0, noise_gyro, size=gyro_p.shape)
    if acc_bias_p is not None:
        acc_p = acc_p + acc_bias_p
    if gyro_bias_p is not None:
        gyro_p = gyro_p + gyro_bias_p
    hdop = None
    sats = None
    if gnss_speed is not None:
        hdop = np.full(n, 1.2)
        sats = np.full(n, 10)
    return ScenarioTruth(
        name=name,
        t=t,
        acc_p=acc_p,
        gyro_p=gyro_p,
        acc_v=acc_v,
        gyro_v=gyro_v,
        R_vp=R_vp,
        q_pv=q,
        gnss_speed=gnss_speed,
        gnss_hdop=hdop,
        gnss_sats=sats,
        notes=notes,
    )


def _sc_stationary(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(3.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    R = rotation_zyx(0.4, -0.3, 1.1)
    return _pack("stationary_phone", t, acc_v, gyro_v, R, "static arbitrary mount", rng=rng)


def _sc_arbitrary_mount(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(8.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    # 2 s static then 1.5 s forward accel then coast
    v = 0.0
    for i, ti in enumerate(t):
        if 2.0 <= ti < 4.5:
            acc_v[i, 0] = 1.6
        if i > 0:
            dt = t[i] - t[i - 1]
            v = max(0.0, v + acc_v[i, 0] * dt)
    R = rotation_zyx(-2.2, 0.55, -1.3)
    speed = np.cumsum(acc_v[:, 0]) / 100.0
    return _pack(
        "arbitrary_mount",
        t,
        acc_v,
        gyro_v,
        R,
        "roll/pitch/yaw all nonzero, then forward accel",
        rng=rng,
        gnss_speed=np.clip(speed, 0, None),
    )


def _sc_straight_accel(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(6.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.5) & (t < 4.0), 0] = 2.0
    R = rotation_zyx(1.2, 0.2, -0.4)
    speed = np.maximum.accumulate(np.clip(np.cumsum(acc_v[:, 0]) / 100.0, 0, None))
    return _pack("straight_acceleration", t, acc_v, gyro_v, R, "sustained ax", rng=rng, gnss_speed=speed)


def _sc_braking(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(7.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.0) & (t < 3.0), 0] = 1.8
    acc_v[(t >= 4.0) & (t < 5.5), 0] = -2.4
    R = rotation_zyx(0.7, -0.15, 0.5)
    speed = np.zeros_like(t)
    v = 0.0
    for i in range(t.size):
        if i:
            v = max(0.0, v + acc_v[i, 0] * 0.01)
        speed[i] = v
    return _pack("braking", t, acc_v, gyro_v, R, "accel then brake", rng=rng, gnss_speed=speed)


def _sc_turning(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(8.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.0) & (t < 2.5), 0] = 1.5
    v = 0.0
    speed = np.zeros_like(t)
    for i, ti in enumerate(t):
        if i:
            v = max(0.0, v + acc_v[i, 0] * 0.01)
        speed[i] = v
        if 3.5 <= ti < 6.5:
            wz = 0.45
            gyro_v[i, 2] = wz
            acc_v[i, 1] = wz * max(v, 0.5)
    R = rotation_zyx(-0.9, 0.1, 0.25)
    return _pack("turning", t, acc_v, gyro_v, R, "accel then left turn", rng=rng, gnss_speed=speed)


def _sc_pothole(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(5.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.2) & (t < 3.0), 0] = 1.4
    idx = int(3.4 * 100)
    acc_v[idx : idx + 4, 2] += np.array([28.0, -18.0, 12.0, -6.0])
    gyro_v[idx : idx + 4, 1] += np.array([3.0, -2.0, 1.2, -0.4])
    R = rotation_zyx(0.3, 0.4, -0.2)
    speed = np.clip(np.cumsum(np.maximum(acc_v[:, 0], 0)) / 100.0, 0, None)
    return _pack("pothole", t, acc_v, gyro_v, R, "shock must not set yaw", rng=rng, gnss_speed=speed)


def _sc_vibration(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(5.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v += rng.normal(0.0, 0.35, size=acc_v.shape)
    gyro_v += rng.normal(0.0, 0.08, size=gyro_v.shape)
    acc_v[(t >= 2.0) & (t < 4.0), 0] += 1.3
    R = rotation_zyx(0.5, -0.5, 0.8)
    return _pack("vibration", t, acc_v, gyro_v, R, "engine vibration", rng=rng)


def _sc_phone_movement(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(6.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.0) & (t < 2.5), 0] = 1.7
    R0 = rotation_zyx(0.2, 0.1, 0.3)
    R1 = rotation_zyx(0.2, 1.2, 1.8)
    R_series = np.repeat(R0[None, ...], t.size, axis=0)
    for i, ti in enumerate(t):
        if 3.0 <= ti < 3.8:
            a = (ti - 3.0) / 0.8
            # slerp via Euler lerp for test fixture only
            ypr0 = np.array([0.2, 0.1, 0.3])
            ypr1 = np.array([0.2, 1.2, 1.8])
            ypr = (1 - a) * ypr0 + a * ypr1
            R_series[i] = rotation_zyx(*ypr)
            gyro_v[i] = np.array([1.5, 1.2, 0.4])
        elif ti >= 3.8:
            R_series[i] = R1
    speed = np.zeros_like(t)
    v = 0.0
    for i in range(t.size):
        v = max(0.0, v + acc_v[i, 0] * 0.01)
        speed[i] = v
    return _pack(
        "phone_movement",
        t,
        acc_v,
        gyro_v,
        R0,
        "user rotates phone after partial calib",
        rng=rng,
        gnss_speed=speed,
        R_series=R_series,
    )


def _sc_weak_accel(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(6.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.5) & (t < 5.0), 0] = 0.12
    R = rotation_zyx(1.0, 0.3, -0.7)
    return _pack("weak_acceleration", t, acc_v, gyro_v, R, "below yaw threshold", rng=rng)


def _sc_gnss_assisted(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(6.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.5) & (t < 4.5), 0] = 1.9
    R = rotation_zyx(2.6, -0.4, 0.9)
    speed = np.zeros_like(t)
    v = 0.0
    for i in range(t.size):
        v = max(0.0, v + acc_v[i, 0] * 0.01)
        speed[i] = v
    return _pack("gnss_assisted", t, acc_v, gyro_v, R, "GNSS dv/dt signs forward", rng=rng, gnss_speed=speed)


def _sc_noisy(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(6.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.5) & (t < 4.0), 0] = 2.1
    R = rotation_zyx(-1.1, 0.35, 0.2)
    speed = np.clip(np.cumsum(acc_v[:, 0]) / 100.0, 0, None)
    return _pack(
        "noisy_imu",
        t,
        acc_v,
        gyro_v,
        R,
        "white IMU noise",
        noise_acc=0.12,
        noise_gyro=0.02,
        rng=rng,
        gnss_speed=speed,
    )


def _sc_gyro_bias(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(6.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.5) & (t < 4.0), 0] = 1.8
    R = rotation_zyx(0.8, -0.25, -0.5)
    speed = np.clip(np.cumsum(acc_v[:, 0]) / 100.0, 0, None)
    return _pack(
        "gyro_bias",
        t,
        acc_v,
        gyro_v,
        R,
        "constant gyro bias in phone frame",
        gyro_bias_p=np.array([0.02, -0.015, 0.03]),
        rng=rng,
        gnss_speed=speed,
    )


def _sc_accel_bias(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(6.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.5) & (t < 4.0), 0] = 1.8
    R = rotation_zyx(-0.4, 0.2, 1.0)
    speed = np.clip(np.cumsum(acc_v[:, 0]) / 100.0, 0, None)
    return _pack(
        "accel_bias",
        t,
        acc_v,
        gyro_v,
        R,
        "constant accel bias",
        acc_bias_p=np.array([0.15, -0.1, 0.08]),
        rng=rng,
        gnss_speed=speed,
    )


def _sc_motion_dropout(rng: np.random.Generator) -> ScenarioTruth:
    t = _time(10.0)
    acc_v, gyro_v = _stationary_vehicle(t.size)
    acc_v[(t >= 1.5) & (t < 3.0), 0] = 2.0
    # long coast with almost no longitudinal evidence
    R = rotation_zyx(0.6, 0.15, -0.35)
    speed = np.zeros_like(t)
    v = 0.0
    for i in range(t.size):
        v = max(0.0, v + acc_v[i, 0] * 0.01)
        speed[i] = v
    return _pack("motion_dropout", t, acc_v, gyro_v, R, "temporary loss of accel evidence", rng=rng, gnss_speed=speed)


def write_scenario_csv(path: str, sc: ScenarioTruth) -> None:
    header = (
        "t,ax_p,ay_p,az_p,gx_p,gy_p,gz_p,"
        "ax_v,ay_v,az_v,gx_v,gy_v,gz_v,"
        "qw,qx,qy,qz,gnss_speed,gnss_hdop,gnss_sats"
    )
    n = sc.t.size
    speed = sc.gnss_speed if sc.gnss_speed is not None else np.full(n, np.nan)
    hdop = sc.gnss_hdop if sc.gnss_hdop is not None else np.full(n, np.nan)
    sats = sc.gnss_sats if sc.gnss_sats is not None else np.full(n, np.nan)
    data = np.column_stack(
        [
            sc.t,
            sc.acc_p,
            sc.gyro_p,
            sc.acc_v,
            sc.gyro_v,
            sc.q_pv,
            speed,
            hdop,
            sats,
        ]
    )
    np.savetxt(path, data, delimiter=",", header=header, comments="")
