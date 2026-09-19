# SIH26168 — Mode-A V2X digital-twin demo

**SIMULATION.** There is no C-V2X/NR-V2X radio, no OBU, and no connection to real vehicles.

The window always shows `SIMULATION`, `V2X RADIO: SIMULATED`, and `Toy filter — not Member 3`.

This application visualizes the existing `sih26168_v2x` library. It does **not** reimplement cooperative localization. Trajectories and errors come from:

```text
V2XSimulator  →  V2XCore.ingest / get_cooperative_measurement
              →  toy baseline EKF  (IMU + AI speed + GNSS)
              →  toy V2X-assisted EKF  (same sensors + gated V2X measurement)
              →  Tkinter digital twin
```

The toy 4-state filters are the same class used by `sih26168_v2x.experiments` (**not** Member 3). Displayed metres are **host simulation**, not a phone or production-EKF claim.

## Story (plain English)

GNSS is lost. Our vehicle keeps moving. Nearby cars send cooperative V2X notes. A bad note shows up. The system spots it and rejects it. Navigation keeps going.

## Launch

From the repository root (Tkinter, Python stdlib — no SDL/pygame):

```bash
python3 -m pip install -r sih26168_v2x/requirements.txt
PYTHONPATH=sih26168_v2x/python:demo python3 -m sih26168_v2x_demo --demo
```

Interactive (paused until START):

```bash
PYTHONPATH=sih26168_v2x/python:demo python3 -m sih26168_v2x_demo --scenario outage_3
```

Scenarios: `normal`, `gnss_outage`, `outage_1`, `outage_3`, `outage_10`, `outage_bad`, `degraded_comms`, `recording`.

## Controls

| Input | Action |
|---|---|
| START / PAUSE or Space | Run / pause |
| DEMO MODE or D | Fixed seed 7, 50 s recording timeline |
| GNSS OUTAGE or G | Force GNSS denied |
| INJECT BAD VEHICLE or B | Offset the next remote broadcast by **+400 m east** |
| 1 / 3 / 10 V2X | Rebuild the sim with that many remotes |
| RESET or R | Restart current scenario |
| Esc | Quit |

More remotes are **not** claimed to be better. The 10-vehicle preset is intended to show whatever the library actually does (including possible degradation).

## Recording timeline (Demo Mode)

Deterministic seed **7**, **3** remotes, `dt = 0.1 s`, duration **50 s**.

| Time | Caption | What the sim does |
|---|---|---|
| 0 s | We are navigating normally. | GNSS on; V2X notes are correlated with GNSS, not double-counted |
| 10 s | GNSS is lost. | GNSS DENIED; IMU/AI continue |
| 12 s | Our vehicle keeps moving without GNSS. | Baseline dead-reckons; V2X-assisted may use cooperative measurement |
| 15 s | Nearby cars send cooperative V2X notes. | Processed links only (messages actually ingested this step) |
| 20 s | A bad observation appears. | One remote shifted **+400 m east** |
| 21 s | NIS gate: the bad note is rejected. | Live Innovation NIS and Decision from the library |
| 27 s | Navigation keeps going. | Rejected note is not used |
| 40–50 s | Final error: baseline vs V2X-assisted. | Endcard with live counts and metres — no fake % gain |

Numbers on screen are live filter errors, not a scripted scoreboard.

## Screen recording (~55 s video)

1. Use a 1600×900 window (native demo size).
2. Launch Demo Mode.
3. Record the window. Example with ffmpeg (Linux/X11):

```bash
# start the demo first, then in another terminal:
ffmpeg -y -video_size 1600x900 -framerate 30 -f x11grab -i :0.0+0,0 \
  -t 55 demo/artifacts/sih26168_v2x_demo.mp4
```

Adjust `+0,0` to the window position (`xwininfo` helps). On Wayland, use the desktop portal / OBS instead.

## SVG stills (headless, no window)

```bash
PYTHONPATH=sih26168_v2x/python:demo python3 -m sih26168_v2x_demo \
  --demo --screenshot demo/artifacts/demo_t12.svg --until 10.2

PYTHONPATH=sih26168_v2x/python:demo python3 -m sih26168_v2x_demo \
  --demo --screenshot demo/artifacts/demo_t21.svg --until 21.2
```

`demo_t12` is the GNSS-outage still (signal lost ~10 s). `demo_t21` is the bad-note reject still.

## Tests

```bash
PYTHONPATH=sih26168_v2x/python:demo python3 -m pytest demo/tests sih26168_v2x/tests/python -q
```

## Performance

The UI targets 60 Hz; the library steps at 10 Hz (`dt_s = 0.1`). Host-only. **Android: not validated.**

## Known limitations

- Visualization only. Not Member 3, not Android, not a real radio. **NOT VALIDATED** on C-V2X, NR-V2X, 5.9 GHz, Android, or real driving.
- Vehicle icons are schematic (top-down), not photorealistic models.
- Per-vehicle link colour uses library `fuse_tracks([one_track])` + `should_use_measurement` — the same functions as the core, not a second algorithm.
- A constant remote GPS bias is largely absorbed in the relative snapshot; the “bad vehicle” demo applies a **sustained +400 m east spoof** after GNSS is denied. The demo engine raises the kinematic jump threshold (`reject_jump_m=500`) so that spoof **reaches the NIS gate** instead of being dropped as an impossible 0.1 s teleport. That is intentional: the clip is about gating, not the jump detector.
- ffmpeg coordinates are machine-specific.

### Recording seed 7 — what the metres actually mean (**SIMULATED**)

Replay is deterministic (three identical runs). GNSS is denied from **t = 10 s**. Spoof is applied only to remote **R1** (+400 m east on the broadcast, not on ego or remote ground truth). Errors are always vs the same ego truth `(east=0, north=16t)` m.

| Epoch | Baseline | V2X-assisted | What the library is doing |
|---|---|---|---|
| t = 20.0 s | 10.23 m | 6.42 m | Fused NIS **33.67** → **REJECT** (`nis_reject`, threshold 9.210). `update_v2x` does not run. |
| t ≈ 20.9 s | ~11.2 m | ~7.4 m | Fused NIS **29.09** (the ~29.10 reject callout). Still **REJECT**. |
| t = 29.8 s | — | — | First post-spoof **DOWNWEIGHT** (NIS 8.70). Cluster still has **3** contributors, including spoofed R1. |
| t = 40.0 s | **35.13 m** | **53.09 m** | Relative snapshots are **30.1 s** old (`relative_snapshot_max_age_s = 30`). Cooperative measurement becomes **UNAVAILABLE**. V2X is worse here because earlier accepted/downweighted fused east (~+125 m) pulled the toy filter east. |
| t = 50.0 s (paused endcard) | **54.70 m** | **33.95 m** | **No V2X measurement after t = 39.9 s.** Both filters share the same IMU/speed from t = 40–50. Shared negative east velocity shrinks the V2X east overshoot and grows the baseline west error. This is not a late cooperative “win”. |

The 40 s / 50 s sign-flip is therefore **mathematically consistent** with snapshot expiry + cluster averaging of the spoofed east, not a second GNSS, not a truth leak, and not a scripted scoreboard. Do not present 50 s as “V2X corrected us in the last 10 seconds”.
