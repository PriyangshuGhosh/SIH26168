# Architecture (MODE A)

**IMPLEMENTED** host library. **SIMULATED** V2X input. **NOT VALIDATED** on radio or Android.

```text
V2X simulator / JSONL replay / in-memory fixture
        ↓
  NormalizedV2XMessage
        ↓
  MockSecurityProvider  (no cryptography)
        ↓
  kinematic / time validation
        ↓
  remote tracks (pseudonyms)
        ↓
  cooperative measurement + covariance
        ↓
  NIS gating  ACCEPT | DOWNWEIGHT | REJECT | UNAVAILABLE
        ↓
  (future) Member 3 EKF   [DESIGNED, not wired]
```

Layers that must stay separate: radio (absent) → transport → decode → validation → cooperative math → fusion.

## Frames

| Frame | Axes | Notes |
|---|---|---|
| WGS84 | lat/lon/alt deg, m | Geographic |
| Local ENU | +X east, +Y north, +Z up | V2X internal |
| Member 3 tangent | north, east | `enuToMember3NorthEast` |
| Member 2 vehicle | +X forward, +Y left, +Z up | Do not change |
| Member 3 velocity | `v_x`, `v_y`, yaw | Uses existing EKF predict(): yaw 0 = North, toward East. At yaw=0, `east_dot = v_y`. That disagrees with Member 2 “+Y left = west when heading north”. This library **does not fix Member 3**; `vehicleFrameToNavigationEnu` copies Member 3. |

## Transports (MODE A)

| Type | Status |
|---|---|
| `SimulatedV2XTransport` | IMPLEMENTED |
| `ReplayV2XTransport` (JSONL) | IMPLEMENTED |
| `InMemoryV2XTransport` | IMPLEMENTED |
| UDP/USB/BT/Android/OBU | NOT IMPLEMENTED |

`IV2XTransport` remains the future plug-in boundary. It is not a radio.

## Member 3 later

See `include/sih26168/v2x/member3_adapter.hpp`. Copy `NavigationState` fields into `LocalNavigationState`. If `GateDecision::Accept` or `Downweight`, apply position NE + `position_cov_ne` as an **optional** measurement. Do not treat it as GNSS. Do not modify Member 3 in this library.

## Privacy

Tracks use short pseudonyms. No persistent vehicle/person identity. In-memory only; timeout prune. Local processing.
