package org.sih26168.idr

data class V2vRemote(
    val id: String,
    val lat: Double,
    val lon: Double,
    val headingRad: Double,
    val vEast: Double,
    val vNorth: Double,
    val ageS: Double,
    val posStdM: Double,
    val usable: Boolean
)

data class V2vSnapshot(
    val libraryStatus: String,
    val androidAdapterStatus: String,
    val transport: String,
    val remotes: List<V2vRemote>,
    val coopReason: String,
    val coopDecision: Int,
    val coopNis: Double,
    val contributing: Int,
    val received: Long,
    val validated: Long,
    val rejected: Long,
    val tracked: Long
)

object V2vBridge {
    @Volatile var nativeAvailable: Boolean = EngineBridge.nativeAvailable
        private set

    @Synchronized external fun nativeLibraryStatus(): String
    @Synchronized external fun nativeAndroidAdapterStatus(): String
    @Synchronized external fun nativeStartSimulated(lat: Double, lon: Double): Boolean
    @Synchronized external fun nativeStop()
    @Synchronized external fun nativePoll(nowS: Double)
    @Synchronized external fun nativeUpdateLocal(
        t: Double, lat: Double, lon: Double, vx: Double, vy: Double, yawRad: Double, gnssAvailable: Boolean
    )
    @Synchronized external fun nativeRemoteCount(): Int
    @Synchronized external fun nativeCopyRemote(index: Int, out: DoubleArray): String
    @Synchronized external fun nativeCoop(out: DoubleArray): String
    @Synchronized external fun nativeHealth(out: LongArray): String

    fun snapshot(nowS: Double, local: NavSnapshot?, gnssAvailable: Boolean): V2vSnapshot {
        val lib = runCatching { nativeLibraryStatus() }.getOrDefault("UNAVAILABLE")
        val android = runCatching { nativeAndroidAdapterStatus() }.getOrDefault("UNAVAILABLE")
        if (!nativeAvailable) {
            return V2vSnapshot(lib, android, "none", emptyList(), "native_unavailable", 3, 0.0, 0, 0, 0, 0, 0)
        }
        if (local != null) {
            nativePoll(nowS)
            nativeUpdateLocal(local.timestamp, local.lat, local.lon, local.speedMps, 0.0,
                Math.toRadians(local.headingDeg), gnssAvailable)
        }
        val n = nativeRemoteCount()
        val remotes = ArrayList<V2vRemote>(n)
        val buf = DoubleArray(8)
        for (i in 0 until n) {
            val id = nativeCopyRemote(i, buf)
            remotes.add(V2vRemote(id, buf[0], buf[1], buf[2], buf[3], buf[4], buf[5], buf[6], buf[7] != 0.0))
        }
        val coop = DoubleArray(6)
        val reason = nativeCoop(coop)
        val health = LongArray(7)
        val transport = nativeHealth(health)
        return V2vSnapshot(lib, android, transport, remotes, reason, coop[0].toInt(), coop[1],
            coop[2].toInt(), health[0], health[1], health[2], health[6])
    }
}
