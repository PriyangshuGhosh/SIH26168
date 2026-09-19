package org.sih26168.idr

data class GeoPoint(val t: Double, val lat: Double, val lon: Double)

/**
 * [OutageRecord.finalDriftMeters] = geodesic(estimated-at-restore, restored GPS).
 * Not last-GPS-before-outage vs new GPS ([gpsDisplacementDuringOutageMeters]).
 */
data class OutageRecord(
    val startTimeS: Double,
    val endTimeS: Double,
    val estimatedAtRestore: GeoPoint,
    val restoredGps: GeoPoint,
    val lastGpsBeforeOutage: GeoPoint?,
    val trail: List<GeoPoint>,
    val simulated: Boolean
) {
    val durationS: Double get() = endTimeS - startTimeS
    val finalDriftMeters: Double
        get() = Geodesic.haversineMeters(
            estimatedAtRestore.lat, estimatedAtRestore.lon, restoredGps.lat, restoredGps.lon
        )
    val gpsDisplacementDuringOutageMeters: Double?
        get() {
            val last = lastGpsBeforeOutage ?: return null
            return Geodesic.haversineMeters(last.lat, last.lon, restoredGps.lat, restoredGps.lon)
        }
}

class OutageTracker {
    @Volatile var inOutage: Boolean = false
        private set
    var lastGps: GeoPoint? = null
        private set
    var lastEstimate: GeoPoint? = null
        private set
    private var lastGpsBefore: GeoPoint? = null
    private var startTime = 0.0
    private var simulated = false
    private val trail = mutableListOf<GeoPoint>()
    private val historyMut = mutableListOf<OutageRecord>()
    private var pendingEstimatedAtRestore: GeoPoint? = null

    val history: List<OutageRecord> @Synchronized get() = historyMut.toList()
    val liveTrail: List<GeoPoint> @Synchronized get() = trail.toList()
    val liveDurationS: Double
        @Synchronized get() = if (!inOutage) 0.0 else (lastEstimate?.t ?: startTime) - startTime

    @Synchronized
    fun reset() {
        inOutage = false
        lastGps = null
        lastEstimate = null
        lastGpsBefore = null
        trail.clear()
        historyMut.clear()
        pendingEstimatedAtRestore = null
    }

    @Synchronized
    fun noteEstimate(t: Double, lat: Double, lon: Double, deadReckoning: Boolean, simulatedOutage: Boolean) {
        if (!lat.isFinite() || !lon.isFinite()) return
        lastEstimate = GeoPoint(t, lat, lon)
        val shouldBeOutage = deadReckoning || simulatedOutage
        if (shouldBeOutage && !inOutage) enter(t, simulatedOutage)
        if (inOutage) trail.add(GeoPoint(t, lat, lon))
        if (!shouldBeOutage && inOutage) pendingEstimatedAtRestore = GeoPoint(t, lat, lon)
    }

    /**
     * [estimateAtRestore]: engine estimate sampled immediately BEFORE the restored fix is fed to the
     * engine. Preferred over polled estimates, because once the fix is fed the engine snaps its output
     * to GNSS and a later poll would make drift ~0 (and 10 Hz polling can race the feed).
     */
    @Synchronized
    fun noteRawGps(
        t: Double, lat: Double, lon: Double, feedToEngine: Boolean,
        estimateAtRestore: GeoPoint? = null
    ): OutageRecord? {
        if (!lat.isFinite() || !lon.isFinite()) return null
        val gps = GeoPoint(t, lat, lon)
        if (!inOutage) {
            lastGps = gps
            return null
        }
        if (!feedToEngine) return null
        val estimated = estimateAtRestore?.takeIf { it.lat.isFinite() && it.lon.isFinite() }
            ?: pendingEstimatedAtRestore ?: lastEstimate ?: gps
        val record = OutageRecord(startTime, t, estimated, gps, lastGpsBefore, trail.toList(), simulated)
        historyMut.add(record)
        inOutage = false
        pendingEstimatedAtRestore = null
        trail.clear()
        lastGps = gps
        return record
    }

    private fun enter(t: Double, simulatedOutage: Boolean) {
        inOutage = true
        simulated = simulatedOutage
        startTime = t
        lastGpsBefore = lastGps
        pendingEstimatedAtRestore = null
        trail.clear()
        lastEstimate?.let { trail.add(it) }
    }
}
