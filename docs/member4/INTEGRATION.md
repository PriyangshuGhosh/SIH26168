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

Member 5 production `libidr_engine` loads this `.roadpack` via `MapMatchingEngine::loadRoadpack`
and calls `match(NavigationState)` on the EKF state. GraphML remains a Python/OSM-extract
artifact; convert it with `python/tools/build_road_database.py` before native init.

**No Member 5 ABI change is required** for matched lat/lon/heading/confidence
(`idr_get_current_state`). Segment id and on-road are extra C getters.

Suggested Member 5 wiring (implemented):

1. Link `sih26168::member4`.
2. Require `map_db_path` to be a readable `.roadpack`.
3. Pass Member 3 `NavigationState` into `MapMatchingEngine::match`.

## Offline map artifact

| Artifact | Producer | Consumer |
|---|---|---|
| `*.graphml` / `*.geojson` | OSM extract / synthetic builder | Python tools |
| `*.sqlite` (R-tree) | `build_road_database.py` | Python spatial queries |
| `*.roadpack` | `build_road_database.py` / `build_synthetic_graph.py` | **C++ runtime** |

`idr_engine_init` may point at a `.roadpack` **or** a `maps/manifest.json` catalog.
Member 6 selects the region that contains the current GNSS fix (`idr_select_map_for_location`).
If the user is outside every provisioned region, the matcher must not snap to a distant city:
`is_on_road_network = false` and the unsnapped navigation position is preserved.
Runtime does not require internet or OSMnx.

Road-network matching data (`.roadpack`) is not the same as map rendering tiles (MBTiles / style JSON).

`MapMatchedPosition` extra fields (appended; original ABI fields unchanged):

- `match_distance_m`
- `map_available`
- `match_valid`
- `match_status` (`OK`, `NO_MAP_DATA`, `OUTSIDE_MAP`, `NO_CANDIDATES`, `REJECTED`, `INVALID_COORDINATES`)

No-match keeps the Member 3 lat/lon. Never `0,0`.

Region catalogs: `sih26168::member4::RegionCatalog` and Python `RoadDataManager`.
Member 5 still uses `idr_select_map_for_location` / `MapCatalog` (compatible manifest).

## Member 6

Member 6 should **not** call Member 4 directly. Consume map-matched lat/lon /
heading / confidence via Member 5 `idr_get_current_state()`
(`docs/member5/INTEGRATION.md`). Use `confidence` and DR flags to style the
marker; do not force-snap in the UI when `is_on_road_network` would be false.

## Adapter note (Member 3)

Member 4 Python `NavigationState` mirrors Member 3 fields. Position uncertainty
is derived from `position_cov_m2` diagonal. No parallel mock schema is required
for integration tests.
