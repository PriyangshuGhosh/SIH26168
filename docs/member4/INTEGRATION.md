# Member 4 → Members 5 & 6 interface

## Types (authoritative)

C++ headers:

- `member4_map_matching/cpp/include/member4/map_matching_types.h`
- `member4_map_matching/cpp/include/member4/MapMatchingEngine.hpp`

`MapMatchedPosition` matches `docs/WORK_DISTRIBUTION.md` and the existing
`member5_engine/include/member5/map_matching_types.h` layout
(`namespace sih26168::member4`).

Input: `sih26168::member3::NavigationState` from Member 3
(`member3_fusion/include/member3/EKFFusionEngine.hpp`).

## C++ usage for Member 5

```cpp
#include "member4/MapMatchingEngine.hpp"

sih26168::member4::MapMatchingEngine matcher;
if (!matcher.loadRoadpack(map_roadpack_path)) {
    // fall back / error
}
auto matched = matcher.match(nav_state);
// matched.lat_snapped, lon_snapped, heading_snapped_rad,
// road_segment_id, confidence_score, is_on_road_network
```

Member 5 currently ships `StubMapMatcher` for parallel development. Replace the
stub by loading Member 4’s `.roadpack` (or keep stub behind a compile flag).
**No Member 5 ABI change is required** if the stub’s `match(NavigationState)`
signature is preserved — Member 4 already uses that shape.

Suggested Member 5 wiring (Member 5 owns this change):

1. Link `sih26168::member4`.
2. Prefer `MapMatchingEngine` when `map_db_path` ends with `.roadpack`.
3. Keep `synthetic:` path behavior for Member 5’s harness if needed.

## Offline map artifact

| Artifact | Producer | Consumer |
|---|---|---|
| `*.graphml` / `*.geojson` | OSM extract / synthetic builder | Python tools |
| `*.sqlite` (R-tree) | `build_road_database.py` | Python spatial queries |
| `*.roadpack` | `build_road_database.py` / `build_synthetic_graph.py` | **C++ runtime** |

`idr_engine_init(map_db_path, ...)` may point at a `.roadpack` file. Runtime
does not require internet or OSMnx.

## Member 6

Member 6 should **not** call Member 4 directly. Consume map-matched lat/lon /
heading / confidence via Member 5 `idr_get_current_state()`
(`docs/member5/INTEGRATION.md`). Use `confidence` and DR flags to style the
marker; do not force-snap in the UI when `is_on_road_network` would be false.

## Adapter note (Member 3)

Member 4 Python `NavigationState` mirrors Member 3 fields. Position uncertainty
is derived from `position_cov_m2` diagonal. No parallel mock schema is required
for integration tests.
