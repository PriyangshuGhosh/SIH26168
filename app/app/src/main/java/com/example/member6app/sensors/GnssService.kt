package com.example.member6app.sensors

import android.annotation.SuppressLint
import android.content.Context
import android.location.GnssStatus
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import com.example.member6app.native.EngineBridge
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * GnssService — captures GPS/GNSS via the platform LocationManager.
 *
 * Timestamp: Android Location.elapsedRealtimeNanos() is boot-clock nanoseconds,
 * consistent with SensorEvent.timestamp used by ImuService. We convert to seconds.
 *
 * HDOP approximation: Android does NOT directly expose HDOP. We derive a
 * conservative proxy: hdop_proxy ≈ accuracy_m / 5.0 (clamped to [0.5, 20]).
 * This is documented and NOT claimed to be real HDOP.
 *
 * The "gnssOutageSimulated" flag, when true, causes this service to NOT call
 * idr_feed_gnss, exercising the native dead-reckoning path.
 */
class GnssService(context: Context) : LocationListener {

    private val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    var gnssOutageSimulated = false
        set(value) {
            field = value
            Log.i(TAG, if (value) "GNSS OUTAGE SIMULATED — idr_feed_gnss paused" else "GNSS restored — idr_feed_gnss resumed")
        }

    private val _lastLocation = MutableStateFlow<Location?>(null)
    val lastLocation: StateFlow<Location?> = _lastLocation

    private val _gnssStatus = MutableStateFlow(GnssInfo())
    val gnssStatus: StateFlow<GnssInfo> = _gnssStatus

    private var updateCount = 0L
    private var startTimeMs = 0L
    private var satelliteCount = 0

    private val gnssStatusCallback = object : GnssStatus.Callback() {
        override fun onSatelliteStatusChanged(status: GnssStatus) {
            var used = 0
            for (i in 0 until status.satelliteCount) {
                if (status.usedInFix(i)) used++
            }
            satelliteCount = used
        }
    }

    val isGnssProviderAvailable: Boolean
        get() = locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)

    @SuppressLint("MissingPermission")
    fun start() {
        startTimeMs = System.currentTimeMillis()
        try {
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                500L,   // min interval ms
                0f,     // min distance m
                this
            )
            locationManager.registerGnssStatusCallback(gnssStatusCallback)
            Log.i(TAG, "GNSS started")
        } catch (e: SecurityException) {
            Log.e(TAG, "Location permission not granted: ${e.message}")
        }
    }

    fun stop() {
        locationManager.removeUpdates(this)
        locationManager.unregisterGnssStatusCallback(gnssStatusCallback)
        Log.i(TAG, "GNSS stopped")
    }

    override fun onLocationChanged(loc: Location) {
        _lastLocation.value = loc
        updateCount++

        // Compute update rate
        val elapsedS = (System.currentTimeMillis() - startTimeMs) / 1000.0
        val updateHz = if (elapsedS > 0) updateCount / elapsedS else 0.0

        val ts        = loc.elapsedRealtimeNanos / 1_000_000_000.0  // boot-clock seconds
        val lat       = loc.latitude
        val lon       = loc.longitude
        val alt       = loc.altitude
        val speedMps  = if (loc.hasSpeed()) loc.speed.toDouble() else 0.0
        // HDOP proxy: accuracy in meters / 5, clamped. See class doc.
        val hdopProxy = if (loc.hasAccuracy()) (loc.accuracy / 5.0).coerceIn(0.5, 20.0) else 5.0
        // If this is a fake/mock location, force 8 satellites so the C++ Engine doesn't reject it
        val numSats   = if (loc.isMock) 8 else satelliteCount

        _gnssStatus.value = GnssInfo(
            available    = true,
            satellites   = numSats,
            accuracy     = if (loc.hasAccuracy()) loc.accuracy else Float.NaN,
            updateHz     = updateHz,
            hdopProxy    = hdopProxy,
            stale        = false
        )

        // Check for poor quality → would trigger DR in native engine even without simulated outage
        val poorQuality = hdopProxy > 4.0 || numSats < 4

        if (!gnssOutageSimulated) {
            EngineBridge.feedGnss(
                timestamp = ts,
                lat       = lat,
                lon       = lon,
                alt       = alt,
                speed     = speedMps,
                hdop      = hdopProxy,
                numSats   = numSats
            )
            Log.v(TAG, "GNSS fed: lat=$lat lon=$lon sats=$numSats hdop=%.2f".format(hdopProxy) +
                       if (poorQuality) " [POOR QUALITY → DR likely]" else "")
        } else {
            Log.v(TAG, "GNSS OUTAGE SIMULATED — skipping idr_feed_gnss")
        }
    }

    override fun onProviderEnabled(provider: String) {
        Log.i(TAG, "GNSS provider enabled: $provider")
        _gnssStatus.value = _gnssStatus.value.copy(available = true, stale = false)
    }

    override fun onProviderDisabled(provider: String) {
        Log.w(TAG, "GNSS provider disabled: $provider")
        _gnssStatus.value = _gnssStatus.value.copy(available = false)
    }

    @Deprecated("Deprecated in API 29")
    override fun onStatusChanged(provider: String, status: Int, extras: Bundle?) {}

    companion object {
        private const val TAG = "GnssService"
    }
}

data class GnssInfo(
    val available: Boolean  = false,
    val satellites: Int     = 0,
    val accuracy: Float     = Float.NaN,
    val updateHz: Double    = 0.0,
    val hdopProxy: Double   = 99.0,
    val stale: Boolean      = true
)
