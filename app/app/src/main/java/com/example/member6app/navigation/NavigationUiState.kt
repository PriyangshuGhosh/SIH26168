package com.example.member6app.navigation

/**
 * NavigationMode mirrors the is_dead_reckoning flag from IDRNavigationOutput
 * and adds UI-friendly states.
 */
enum class NavigationMode {
    INITIALIZING,       // Engine not yet initialized
    GNSS_AIDED,         // is_dead_reckoning == 0
    DEAD_RECKONING,     // is_dead_reckoning == 1 (normal outage / poor GNSS)
    GNSS_OUTAGE_SIM,    // Simulated outage (user-triggered demo mode)
    ENGINE_FAILED,      // Native init returned 0 or threw
    NO_FIX              // Engine running but no valid position yet
}

enum class SensorMode {
    REAL_DEVICE,        // Live Android sensors + native engine
    REPLAY_DEMO         // Deterministic replay (future)
}

data class NavigationUiState(
    val mode:             NavigationMode = NavigationMode.INITIALIZING,
    val sensorMode:       SensorMode     = SensorMode.REAL_DEVICE,

    // Position
    val latitude:         Double = 0.0,
    val longitude:        Double = 0.0,

    // Kinematics
    val speedKmh:         Double = 0.0,
    val headingDeg:       Double = 0.0,

    // Quality
    val confidence:       Double = 0.0,
    val gnssAvailable:    Boolean = false,
    val gnssSatellites:   Int = 0,
    val gnssAccuracy:     Float = Float.NaN,

    // Vision (auxiliary — PENDING MEMBER3)
    val visionConfidence: Double = 0.0,
    val visionStatus:     String = "UNINIT",

    // Diagnostics
    val imuHz:            Double = 0.0,
    val cameraFps:        Double = 0.0,
    val engineError:      String = "",
    val engineInitialized: Boolean = false,
    val mapStatus:        String = "NOT_LOADED",
    val speedValid:       Boolean = false,
    val speedLabel:       String = "Speed unavailable",
    val simulation:       Boolean = false,
    val mapMessage:       String = ""
) {
    val modeLabel: String get() = when {
        simulation && mode == NavigationMode.GNSS_OUTAGE_SIM -> "SIMULATION — GNSS OUTAGE"
        simulation && mode == NavigationMode.DEAD_RECKONING -> "SIMULATION — DEAD RECKONING"
        simulation && mode == NavigationMode.GNSS_AIDED -> "SIMULATION — GNSS AIDED"
        mode == NavigationMode.INITIALIZING    -> "INITIALIZING"
        mode == NavigationMode.GNSS_AIDED      -> "GNSS AIDED"
        mode == NavigationMode.DEAD_RECKONING  -> "DEAD RECKONING"
        mode == NavigationMode.GNSS_OUTAGE_SIM -> "GNSS OUTAGE — DEAD RECKONING"
        mode == NavigationMode.ENGINE_FAILED   -> "ENGINE FAILED"
        mode == NavigationMode.NO_FIX          -> "NO FIX"
        else -> mode.name
    }

    val gnssLabel: String get() = when {
        !gnssAvailable                 -> "UNAVAILABLE"
        mode == NavigationMode.GNSS_OUTAGE_SIM -> "SIMULATED OUTAGE"
        mode == NavigationMode.GNSS_AIDED      -> "ACTIVE ($gnssSatellites sats)"
        else                           -> "LOST"
    }
}
