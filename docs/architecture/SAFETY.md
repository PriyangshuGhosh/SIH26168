# Speed and map safety

Defaults: `member5_engine/config/safety.json`.

## Impossible speed (~700 km/h)

194.4 m/s is rejected before it can become a trusted published speed:

1. Member 5 `SpeedValidityFilter` rejects non-finite, negative, `> max_vehicle_speed_mps` (55), and jumps using **actual dt**.
2. AI variance 0 / NaN / Inf / tiny is rejected (`VarianceInvalid`).
3. Member 3 EKF NIS-gates AI speed and also rejects `velocity > max_vehicle_speed_mps`.
4. Published `IDRNavigationOutput.speed_m_s` is the last trusted finite speed; `idr_speed_is_valid()` is 0 and confidence is reduced.
5. UI must show **Speed unavailable** when invalid. It must not clamp 700 km/h to a fake 120 km/h.

## Wrong city + high confidence

1. Runtime loads only provisioned `.roadpack` or a `maps/manifest.json` catalog.
2. Region selection uses GNSS lat/lon against catalog bounds.
3. Matcher search radius is capped (`max_search_radius_m` = 120).
4. Positions outside geographic bounds are **not** snapped; output stays at the navigation lat/lon with `is_on_road_network = false` and message **MAP DATA NOT AVAILABLE**.
5. No OSM download during GNSS outage.

Coverage is only the packages actually shipped (currently a synthetic grid fixture for tests/demo), not worldwide cities.
