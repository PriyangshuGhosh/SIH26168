# Member 5 test data

`synthetic_e2e_log.csv` is **generated** by `member5_synthetic_e2e` and is gitignored;
nothing here needs to be committed.

## Scenario

40 s synthetic drive on a pure north-south road at lon 77.5946:

| Window | What happens |
|---|---|
| 0-3 s | Static (lets Member 2 lock gravity) |
| 3-9 s | Constant 2.5 m/s2 accel to 15 m/s (lets Member 2 observe yaw) |
| 9-20 s | Cruise, GNSS at 1 Hz |
| 20-35 s | Tunnel: no GNSS, engine must hold dead reckoning |
| 35-40 s | GNSS reacquired, engine must exit DR |

IMU is fed at 100 Hz; the log is sampled every 10th IMU sample (10 Hz), matching the
rate Member 6 polls `idr_get_current_state`.

## Columns

| Column | Meaning |
|---|---|
| `t` | Engine state timestamp (s) |
| `gt_lat`, `gt_lon`, `gt_speed` | Ground truth from the scenario generator |
| `est_lat`, `est_lon`, `est_speed` | Engine output |
| `dr` | `1` while dead reckoning, `0` when GNSS-aided |
| `confidence` | `IDRNavigationOutput.confidence` |
| `err_m` | Horizontal error between truth and estimate (m) |
