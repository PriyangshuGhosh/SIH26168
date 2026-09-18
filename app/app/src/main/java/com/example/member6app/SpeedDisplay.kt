package com.example.member6app

object SpeedUnits {
    fun mpsToKmh(mps: Double): Double = mps * 3.6
}

object SpeedDisplay {
    const val MAX_DISPLAY_MPS = 55.0

    fun formatKmh(speedMps: Double, valid: Boolean): String {
        if (!valid || !speedMps.isFinite() || speedMps < 0.0 || speedMps > MAX_DISPLAY_MPS) {
            return "Speed unavailable"
        }
        return String.format("%.1f km/h", SpeedUnits.mpsToKmh(speedMps))
    }
}
