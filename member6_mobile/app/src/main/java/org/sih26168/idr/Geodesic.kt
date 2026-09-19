package org.sih26168.idr

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/** WGS84 equatorial radius (same as sih26168::v2x::kEarthRadiusM). */
object Geodesic {
    const val EARTH_RADIUS_M = 6_378_137.0

    fun haversineMeters(lat1Deg: Double, lon1Deg: Double, lat2Deg: Double, lon2Deg: Double): Double {
        if (!lat1Deg.isFinite() || !lon1Deg.isFinite() || !lat2Deg.isFinite() || !lon2Deg.isFinite()) {
            return Double.NaN
        }
        val p1 = Math.toRadians(lat1Deg)
        val p2 = Math.toRadians(lat2Deg)
        val dPhi = p2 - p1
        val dLam = Math.toRadians(lon2Deg - lon1Deg)
        val a = sin(dPhi / 2).pow(2.0) + cos(p1) * cos(p2) * sin(dLam / 2).pow(2.0)
        return EARTH_RADIUS_M * 2.0 * asin(min(1.0, sqrt(a)))
    }
}
