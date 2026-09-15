# Member 2 — Full deliverable map

This module covers the Member 2 contract in `docs/WORK_DISTRIBUTION.md`.

| # | Topic | Where |
|---|---|---|
| 1 | Quasi-static detection | `frame_aligner.py` / `FrameAligner.cpp`, config in `FrameAlignerConfig` |
| 2 | Gravity / roll / pitch | gravity EMA + `rotationGravityUpToVehicleZ` |
| 3 | Yaw from motion evidence only | PCA of `a_h` + GNSS `dv/dt` sign + optional turn 180° check |
| 4 | DCM / quaternion | `frames.py`, Eigen helpers |
| 5 | Synthetic + recorded hooks | `simulator.py`, `tests/data/`, `validate_recorded.py` |
| 6 | Python reference | `member2_alignment/python/` |
| 7 | C++20/Eigen | `member2_alignment/cpp/` |
| 8 | Confidence / status | `STATUS_AND_CONFIDENCE.md` |
| 9 | Deterministic vectors | `generate_test_vectors.py` (seed 26168) |
| 10 | Benchmark | `member2_benchmark` |
| 11 | Integration | `INTEGRATION.md` |
| 12 | Input validation | NaN/Inf/time/magnitude/gaps documented in `ROTATION_CONVENTIONS.md` |
| 13–16 | Tests | `tests/python`, `cpp/tests` |
| 17 | Synthetic data | `tests/data/generated/` |
| 18 | Recorded data | **NOT VALIDATED** — no log in repo; see `tests/data/recorded/README.md` |
| 19 | Python/C++ equivalence | `test_cross_language.py` (atol 1e-6) |
| 20 | 100 Hz benchmark | desktop only; Android **NOT VALIDATED** |

**Gravity determines roll/pitch but not absolute yaw.**
