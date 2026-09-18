# Member 5 test data

`synthetic_e2e_log.csv` is **generated** by `member5_synthetic_e2e` and should not be treated as field data.

## Scenario

30 s synthetic drive on Member 4 `synthetic_grid.roadpack` (origin 12.9716, 77.5946). Distance stays inside the ~240 m grid.

| Window | What happens |
|---|---|
| 0-3 s | Static (Member 2 gravity) |
| 3-7 s | Accel to 8 m/s |
| 7-16 s | Cruise, GNSS at 1 Hz |
| 16-24 s | Tunnel: no GNSS; deficit SM + EKF dead reckoning |
| 24-30 s | GNSS reacquired |

IMU is **100 Hz**. Member 5 packs Member 1 windows at that same rate (T=200 samples = 2 s, stride 10). The engine uses **real** Member 2, Member 3 EKF, and Member 4 `MapMatchingEngine`. Member 1 is the **explicit** `"mock"` estimator unless ONNX Runtime + `speed_estimator.onnx` are provided.

`dummy_speed_estimator.onnx` is a **wiring fixture** (Member 1 I/O names, `[1,200,6]` at 100 Hz). It is not a trained speed model. Regenerate with `python3 member5_engine/scripts/make_dummy_onnx.py`.

## Columns

Same as before: `t,gt_*,est_*,dr,confidence,err_m`.
