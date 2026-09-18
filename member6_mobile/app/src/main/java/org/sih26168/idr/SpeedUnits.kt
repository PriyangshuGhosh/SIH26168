package org.sih26168.idr

/** Canonical speed is m/s. Display km/h uses this helper only. */
object SpeedUnits {
    const val MPS_TO_KMH = 3.6
    const val KMH_TO_MPS = 1.0 / 3.6

    fun mpsToKmh(speedMps: Double): Double = speedMps * MPS_TO_KMH
    fun kmhToMps(speedKmh: Double): Double = speedKmh * KMH_TO_MPS
}
