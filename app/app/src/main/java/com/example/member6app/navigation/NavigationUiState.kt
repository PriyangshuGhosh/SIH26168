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
    val mapStatus:        String = "NOT_LOADED"
) {
    val modeLabel: String get() = when (mode) {
        NavigationMode.INITIALIZING    -> "INITIALIZING"
        NavigationMode.GNSS_AIDED      -> "GNSS AIDED"
        NavigationMode.DEAD_RECKONING  -> "DEAD RECKONING"
        NavigationMode.GNSS_OUTAGE_SIM -> "GNSS OUTAGE — DEAD RECKONING"
        NavigationMode.ENGINE_FAILED   -> "ENGINE FAILED"
        NavigationMode.NO_FIX          -> "NO FIX"
    }

    val gnssLabel: String get() = when {
        !gnssAvailable                 -> "UNAVAILABLE"
        mode == NavigationMode.GNSS_OUTAGE_SIM -> "SIMULATED OUTAGE"
        mode == NavigationMode.GNSS_AIDED      -> "ACTIVE ($gnssSatellites sats)"
        else                           -> "LOST"
    }
}
