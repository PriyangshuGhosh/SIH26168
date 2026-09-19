package org.sih26168.idr

/**
 * Display layer only. Does not clamp 700 km/h to 120.
 * Invalid / non-finite / out-of-range values become unavailable.
 */
object SpeedDisplay {
    /* Display envelope (~198 km/h) matches the native demo vehicle bound. */
    const val MAX_DISPLAY_MPS = 55.0

    fun formatKmh(speedMps: Double, valid: Boolean): String {
        if (!valid || !speedMps.isFinite() || speedMps < 0.0 || speedMps > MAX_DISPLAY_MPS) {
            return "Speed unavailable"
        }
        val kmh = SpeedUnits.mpsToKmh(speedMps)
        return String.format("%.1f km/h", kmh)
    }
}
