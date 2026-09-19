# Hardware integration

**MODE A: no hardware. DESIGNED / NOT VALIDATED. No supported devices.**

A normal Android phone does **not** receive C-V2X/5.9 GHz V2V.

India (public policy, not a lab result): DoT G.S.R. 466(E) (June 2026) licence-exempt C-V2X **OBU** operation in **5875–5905 MHz** (non-interference / non-protection). RSUs are a separate authorization topic. Equipment type approval still applies. This library does **not** implement that radio.

Candidate **classes** (not purchased, not tested, not “supported”):

- Aftermarket C-V2X OBU that exposes decoded kinematics on IP/serial
- Linux gateway between OBU and phone (Wi-Fi/USB network)
- Vendor SDK on a dedicated automotive unit

Before any purchase, verify: decoded CAM/BSM-like kinematics over a documented socket/serial schema; latency; India type approval; that the phone only consumes **already decoded** messages.

Phases: simulator → replay → local JSONL/loopback → (later) gateway → (later) OBU. Same `NormalizedV2XMessage` / `V2XCore`.
