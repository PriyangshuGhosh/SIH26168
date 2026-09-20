package com.vizag.nav

enum class NavMode { INITIALIZING, GPS, DEAD_RECKONING }

enum class TravelMode { VEHICLE, WALK }

enum class AppTheme { DARK_BLUE, LIGHT }

data class NavState(
    val mode: NavMode = NavMode.INITIALIZING,
    val lat: Double = 17.6868,
    val lon: Double = 83.2185,
    val speedMps: Float = 0f,
    val headingDeg: Float = 0f,
    val speedConfidence: Float = 0f,
    val accuracyM: Float = 0f,
    val lastGpsFix: Long = 0L,
    
    // Settings & UI state
    val travelMode: TravelMode = TravelMode.VEHICLE,
    val theme: AppTheme = AppTheme.LIGHT,
    val destination: String = "",
    val destinationPt: Pair<Double, Double>? = null,
    
    // Dev Options Telemetry
    val isImuActive: Boolean = false,
    val isOnnxReady: Boolean = false,
    val isGnssActive: Boolean = false,
    
    // Member functionality dashboard logs
    val dashboardLogs: List<String> = emptyList()
) {
    val isGpsStale: Boolean get() = System.currentTimeMillis() - lastGpsFix > 10000L // Increased to 10 seconds to prevent flapping
    val modeLabel: String get() = when (mode) {
        NavMode.INITIALIZING -> "Initializing..."
        NavMode.GPS          -> "GPS Active"
        NavMode.DEAD_RECKONING -> "Dead Reckoning (ML)"
    }

    companion object {
        val VIZAG_CENTER_LAT = 17.6868
        val VIZAG_CENTER_LON = 83.2185
    }
}
