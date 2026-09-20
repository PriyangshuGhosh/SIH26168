package com.vizag.nav

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Wraps Android LocationManager to deliver GNSS fixes.
 * Emits null when no fix is available.
 */
class GnssManager(context: Context) {

    data class GnssData(
        val lat: Double,
        val lon: Double,
        val speedMps: Float,    // m/s; 0f when not available
        val bearingDeg: Float,  // degrees, 0 = North; 0f when not available
        val accuracyM: Float,
        val hasSpeed: Boolean,
        val hasBearing: Boolean,
        val fixTimeMs: Long
    ) {
        val speedKmh: Float get() = speedMps * 3.6f
    }

    private val _data = MutableStateFlow<GnssData?>(null)
    val data: StateFlow<GnssData?> = _data.asStateFlow()

    private val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    private val listener = object : LocationListener {
        override fun onLocationChanged(loc: Location) {
            _data.value = GnssData(
                lat        = loc.latitude,
                lon        = loc.longitude,
                speedMps   = if (loc.hasSpeed()) loc.speed else 0f,
                bearingDeg = if (loc.hasBearing()) loc.bearing else 0f,
                accuracyM  = if (loc.hasAccuracy()) loc.accuracy else 0f,
                hasSpeed   = loc.hasSpeed(),
                hasBearing = loc.hasBearing(),
                fixTimeMs  = System.currentTimeMillis()
            )
        }
        @Deprecated("Unused")
        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
        override fun onProviderEnabled(provider: String) = Unit
        override fun onProviderDisabled(provider: String) = Unit
    }

    @SuppressLint("MissingPermission")
    fun start() {
        // Register GPS_PROVIDER ONLY — NETWORK_PROVIDER uses accelerometer-fused sensor fusion
        // which causes speed to spike when the phone is shaken. Pure GPS Doppler is shake-immune.
        if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
            lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 500L, 0f, listener)
        }
    }

    fun stop() {
        lm.removeUpdates(listener)
    }

    /** Temporarily suppress forwarding fixes — used to simulate GPS outage. */
    fun setFeedEnabled(enabled: Boolean) {
        if (!enabled) _data.value = null
    }
}
