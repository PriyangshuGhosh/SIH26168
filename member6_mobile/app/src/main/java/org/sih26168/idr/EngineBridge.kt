package org.sih26168.idr

data class NavSnapshot(
    val timestamp: Double,
    val lat: Double,
    val lon: Double,
    val headingDeg: Double,
    val speedMps: Double,
    val isDeadReckoning: Boolean,
    val confidence: Double,
    val speedValid: Boolean,
    val speedRejectReason: String,
    val mapStatus: String,
    val onRoad: Boolean,
    val regionId: String,
    val roadSegmentId: Long = 0L,
    val speedBackend: String = ""
)

data class EngineDiagnostics(
    val rawGnssSpeedMps: Double = Double.NaN,
    val aiSpeedMps: Double = Double.NaN,
    val ekfSpeedMps: Double = Double.NaN,
    val displayedSpeedMps: Double = Double.NaN,
    val speedValid: Boolean = false,
    val mapStatusCode: Int = 0,
    val calibrationStatus: Int = 0,
    val lastAiAccepted: Boolean = false,
    val imuHz: Double = Double.NaN,
    val lastImuTimestamp: Double = Double.NaN,
    val lastGnssTimestamp: Double = Double.NaN
)

interface EnginePort {
    fun init(mapPath: String, onnxPath: String): Boolean
    fun shutdown()
    fun feedImu(t: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double)
    fun feedGnss(t: Double, lat: Double, lon: Double, alt: Double, speedMps: Double, hdop: Double, sats: Int)
    fun poll(): NavSnapshot?
    fun selectMap(lat: Double, lon: Double): Boolean
    fun mapCovers(lat: Double, lon: Double): Boolean
    fun diagnostics(): EngineDiagnostics
    fun lastError(): String
    fun isInitialized(): Boolean
}

object EngineBridge : EnginePort {
    @Volatile var nativeAvailable: Boolean = false
        private set

    init {
        try {
            System.loadLibrary("idr_jni")
            nativeAvailable = true
        } catch (_: UnsatisfiedLinkError) {
            nativeAvailable = false
        }
    }

    @Synchronized external fun nativeInit(mapPath: String, onnxPath: String): Boolean
    @Synchronized external fun nativeShutdown()
    @Synchronized external fun nativeFeedImu(t: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double)
    @Synchronized external fun nativeFeedGnss(t: Double, lat: Double, lon: Double, alt: Double, speedMps: Double, hdop: Double, sats: Int)
    @Synchronized external fun nativePoll(out: DoubleArray): Boolean
    @Synchronized external fun nativeSelectMap(lat: Double, lon: Double): Boolean
    @Synchronized external fun nativeMapCovers(lat: Double, lon: Double): Boolean
    @Synchronized external fun nativeSpeedValid(): Boolean
    @Synchronized external fun nativeSpeedRejectReason(): String
    @Synchronized external fun nativeMapStatus(): String
    @Synchronized external fun nativeRegionId(): String
    @Synchronized external fun nativeOnRoad(): Boolean
    @Synchronized external fun nativeRoadSegmentId(): Long
    @Synchronized external fun nativeSpeedBackend(): String
    @Synchronized external fun nativeLastError(): String
    @Synchronized external fun nativeIsInitialized(): Boolean
    @Synchronized external fun nativeDiagnostics(out: DoubleArray): Boolean

    override fun init(mapPath: String, onnxPath: String): Boolean =
        if (nativeAvailable) nativeInit(mapPath, onnxPath) else false

    override fun shutdown() { if (nativeAvailable) nativeShutdown() }

    override fun feedImu(t: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double) {
        if (nativeAvailable) nativeFeedImu(t, ax, ay, az, gx, gy, gz)
    }

    override fun feedGnss(t: Double, lat: Double, lon: Double, alt: Double, speedMps: Double, hdop: Double, sats: Int) {
        if (nativeAvailable) nativeFeedGnss(t, lat, lon, alt, speedMps, hdop, sats)
    }

    override fun poll(): NavSnapshot? {
        if (!nativeAvailable) return null
        val buf = DoubleArray(8)
        if (!nativePoll(buf)) return null
        return NavSnapshot(
            timestamp = buf[0], lat = buf[1], lon = buf[2], headingDeg = buf[3], speedMps = buf[4],
            isDeadReckoning = buf[5] != 0.0, confidence = buf[6],
            speedValid = nativeSpeedValid(), speedRejectReason = nativeSpeedRejectReason(),
            mapStatus = nativeMapStatus(), onRoad = buf[7] != 0.0, regionId = nativeRegionId(),
            roadSegmentId = nativeRoadSegmentId(), speedBackend = nativeSpeedBackend()
        )
    }

    override fun selectMap(lat: Double, lon: Double): Boolean =
        nativeAvailable && nativeSelectMap(lat, lon)

    override fun mapCovers(lat: Double, lon: Double): Boolean =
        nativeAvailable && nativeMapCovers(lat, lon)

    override fun diagnostics(): EngineDiagnostics {
        if (!nativeAvailable) return EngineDiagnostics()
        val d = DoubleArray(11)
        if (!nativeDiagnostics(d)) return EngineDiagnostics()
        return EngineDiagnostics(d[0], d[1], d[2], d[3], d[4] != 0.0, d[5].toInt(), d[6].toInt(),
            d[7] != 0.0, d[8], d[9], d[10])
    }

    override fun lastError(): String = if (nativeAvailable) nativeLastError() else "native library not loaded"
    override fun isInitialized(): Boolean = nativeAvailable && nativeIsInitialized()
}
