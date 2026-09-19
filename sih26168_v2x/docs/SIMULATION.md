# Simulation (MODE A)

The simulator is first-class. It is **not** a C-V2X stack.

Each remote has **ground truth** and a **broadcast estimate** (truth + configurable noise/bias). The localizer never receives ego ground truth.

Imperfections (config, not algorithm constants): packet loss, latency mean/jitter, position/velocity σ, out-of-order, duplicates, stale/timestamp error, remote GPS bias, bad messages.

Scenarios (Python `SCENARIOS`): straight, curved, highway, urban, intersection, convoy, overtaking, lane_change, braking, acceleration, sparse, dense.

Deterministic if `seed` is fixed.

Replay: JSONL through the same `ingest()` path as live simulated messages.

```bash
PYTHONPATH=sih26168_v2x/python python3 -c "from sih26168_v2x.simulator import V2XSimulator, scenario; V2XSimulator(scenario('convoy')).write_jsonl('/tmp/v2x.jsonl', 5)"
```
