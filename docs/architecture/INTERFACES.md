# End-to-end interface table

| Stage | Type | Units | Frame | Timestamp | Validity / confidence | Owner |
|---|---|---|---|---|---|---|
| Android accel | float[3] | m/s² | phone | SensorEvent ns → s once | drop regression/duplicates | M6 |
| Android gyro | float[3] | rad/s | phone | same clock | pair within ~8 ms of accel | M6 |
| Android GNSS | lat/lon/speed | deg, m/s | WGS84 | elapsedRealtime ns → s | HDOP/sats in engine | M6 |
| M2 `AlignedIMUFrame` | doubles | m/s², rad/s | vehicle +X fwd | seconds | CalibrationStatus | M2 |
| M1 window | float [T,6] | accel in g (engine converts), gyro rad/s | vehicle | last sample time | valid flag | M5→M1 |
| M1 output | velocity, variance | m/s, m²/s² | vehicle forward | window end | variance usable | M1 |
| M3 `NavigationState` | lat/lon, vx/vy, yaw | deg, m/s, rad | local tangent + WGS84 | seconds | NIS gates, mode | M3 |
| M4 `MapMatchedPosition` | snapped lat/lon | deg | WGS84 | nav timestamp | confidence, is_on_road | M4 |
| M5 `IDRNavigationOutput` | lat/lon, heading_deg, speed_m_s | deg, deg, m/s | WGS84 | seconds | speed_valid, map_status | M5 |
| M6 UI | km/h | m/s × 3.6 | display only | poll ~10 Hz | "Speed unavailable" if invalid | M6 |

UI conversion is centralized (`SpeedUnits` / `member5/SpeedUnits.hpp`). Do not invent a second factor.
