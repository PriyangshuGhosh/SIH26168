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
    val regionId: String
)

/**
 * JNI boundary. Field copies are explicit so IDRNavigationOutput padding cannot leak.
 * IMU pairing happens in ImuService, not here, to keep the native call one 6-axis sample.
 */
object EngineBridge {
    init {
        try {
            System.loadLibrary("idr_jni")
        } catch (_: UnsatisfiedLinkError) {
            try {
                System.loadLibrary("idr_engine")
            } catch (_: UnsatisfiedLinkError) {
                // Host unit tests do not load native code.
            }
        }
    }

    external fun nativeInit(mapPath: String, onnxPath: String): Boolean
    external fun nativeShutdown()
    external fun nativeFeedImu(t: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double)
    external fun nativeFeedGnss(t: Double, lat: Double, lon: Double, alt: Double, speedMps: Double, hdop: Double, sats: Int)
    external fun nativePoll(
        out: DoubleArray
    ): Boolean

    external fun nativeSelectMap(lat: Double, lon: Double): Boolean
    external fun nativeSpeedValid(): Boolean
    external fun nativeSpeedRejectReason(): String
    external fun nativeMapStatus(): String
    external fun nativeRegionId(): String
    external fun nativeOnRoad(): Boolean
    external fun nativeDiagnostics(out: DoubleArray): Boolean

    fun pollSnapshot(): NavSnapshot? {
        val buf = DoubleArray(8)
        if (!nativePoll(buf)) return null
        val valid = nativeSpeedValid()
        return NavSnapshot(
            timestamp = buf[0],
            lat = buf[1],
            lon = buf[2],
            headingDeg = buf[3],
            speedMps = buf[4],
            isDeadReckoning = buf[5] != 0.0,
            confidence = buf[6],
            speedValid = valid,
            speedRejectReason = nativeSpeedRejectReason(),
            mapStatus = nativeMapStatus(),
            onRoad = nativeOnRoad(),
            regionId = nativeRegionId()
        )
    }
}
