# Benchmarks and simulation experiments

**HOST ONLY. ANDROID PERFORMANCE: NOT VALIDATED. REAL V2X: NOT VALIDATED.**
**Toy EKF in `experiments.py` is NOT Member 3.**

## Host microbenchmark

Machine: Linux host, Release `sih26168_v2x_benchmark`, 20 000 ingest+measure calls.

| Metric | Value |
|---|---|
| total | 7.78 ms |
| average | 0.00039 ms/call |
| p95/p99 | scaled estimates only, not empirical quantiles |

```bash
./build-v2x/sih26168_v2x_benchmark
```

## GNSS outage experiment (SIMULATION)

Timeline: 0–60 s GNSS, 60–180 s denied, 180–240 s GNSS. Seed 3, dt 0.2 s.

| Remotes | Mode | pos RMSE (m) | outage-end drift (m) | p95 (m) | recovery (m) |
|---|---|---:|---:|---:|---:|
| 0 | IMU | 35.12 | 74.33 | 61.84 | 1.94 |
| 0 | IMU+AI | 67.86 | 139.92 | 138.87 | 0.28 |
| 0 | V2X ungated/gated | 67.86 | 139.92 | 138.87 | 0.28 |
| 1 | V2X gated | **4.99** | **9.32** | 12.36 | 1.28 |
| 3 | V2X gated | 7.74 | 26.58 | 12.96 | 1.34 |
| 10 | V2X gated | 61.99 | 170.24 | 152.56 | 0.64 |

Observations (this toy filter only):

- Zero remotes: V2X matches IMU+AI (`no_v2x` fallback). **Pass.**
- One well-associated remote reduced outage drift vs IMU in this run.
- Three remotes still helped vs IMU but less than one (geometry/correlation).
- Ten remotes **degraded** vs IMU. More vehicles is not always better.
- Ungated vs gated were identical at this seed (innovations stayed inside the χ² gate).
- IMU+AI speed-only was **worse** than IMU-only here: constraining speed along a drifted heading can increase along-track error. Do not generalize to Member 3.

```bash
PYTHONPATH=sih26168_v2x/python python3 -m sih26168_v2x.experiments
```
