package org.sih26168.idr

import java.io.File
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

data class ReplayEvent(
    val type: String,
    val t: Double,
    val ax: Double = 0.0,
    val ay: Double = 0.0,
    val az: Double = 0.0,
    val gx: Double = 0.0,
    val gy: Double = 0.0,
    val gz: Double = 0.0,
    val lat: Double = Double.NaN,
    val lon: Double = Double.NaN,
    val alt: Double = 0.0,
    val speed: Double = Double.NaN, /* NaN = no speed reported (unknown, not 0 m/s) */
    val hdop: Double = 1.0,
    val sats: Int = 8,
    val outage: Boolean = false
)

object ReplayParser {
    fun parseJsonl(text: String): List<ReplayEvent> {
        val out = mutableListOf<ReplayEvent>()
        for (raw in text.lineSequence()) {
            val line = raw.trim()
            if (line.isEmpty() || !line.startsWith("{")) continue
            fun num(key: String): Double {
                val p = line.indexOf("\"$key\"")
                if (p < 0) return Double.NaN
                val c = line.indexOf(':', p)
                val s = line.substring(c + 1).trim().takeWhile { it.isDigit() || it == '-' || it == '.' || it == 'e' || it == 'E' }
                return s.toDoubleOrNull() ?: Double.NaN
            }
            fun str(key: String): String {
                val p = line.indexOf("\"$key\"")
                if (p < 0) return ""
                val c = line.indexOf(':', p)
                val q1 = line.indexOf('"', c + 1)
                val q2 = line.indexOf('"', q1 + 1)
                return if (q1 >= 0 && q2 > q1) line.substring(q1 + 1, q2) else ""
            }
            fun bool(key: String): Boolean {
                val p = line.indexOf("\"$key\"")
                if (p < 0) return false
                return line.substring(p).contains("true")
            }
            val type = str("type")
            val t = num("t")
            if (!t.isFinite()) continue
            out.add(
                ReplayEvent(
                    type = type, t = t,
                    ax = num("ax").takeIf { it.isFinite() } ?: 0.0,
                    ay = num("ay").takeIf { it.isFinite() } ?: 0.0,
                    az = num("az").takeIf { it.isFinite() } ?: 9.81,
                    gx = num("gx").takeIf { it.isFinite() } ?: 0.0,
                    gy = num("gy").takeIf { it.isFinite() } ?: 0.0,
                    gz = num("gz").takeIf { it.isFinite() } ?: 0.0,
                    lat = num("lat"), lon = num("lon"), alt = num("alt").takeIf { it.isFinite() } ?: 0.0,
                    speed = num("speed"),
                    hdop = num("hdop").takeIf { it.isFinite() } ?: 1.0,
                    sats = num("sats").toInt().takeIf { it > 0 } ?: 8,
                    outage = bool("active") || type == "outage" && bool("outage")
                )
            )
        }
        return out
    }
}

class SessionLogger(private val file: File) {
    private val lock = ReentrantLock()
    fun append(line: String) = lock.withLock {
        file.parentFile?.mkdirs()
        file.appendText(line.trimEnd() + "\n")
    }
    fun imu(t: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double) {
        append("""{"type":"imu","t":$t,"ax":$ax,"ay":$ay,"az":$az,"gx":$gx,"gy":$gy,"gz":$gz}""")
    }
    fun gnss(t: Double, lat: Double, lon: Double, alt: Double, speed: Double, hdop: Double, sats: Int) {
        val speedField = if (speed.isFinite()) ""","speed":$speed""" else "" // omitted = unknown
        append("""{"type":"gnss","t":$t,"lat":$lat,"lon":$lon,"alt":$alt$speedField,"hdop":$hdop,"sats":$sats}""")
    }
    fun outage(t: Double, active: Boolean) {
        append("""{"type":"outage","t":$t,"active":$active}""")
    }
}

class ReplayPlayer(private val engine: EnginePort) {
    fun run(events: List<ReplayEvent>, onOutage: (Boolean) -> Unit = {}) {
        var withholdGnss = false
        for (e in events) {
            when (e.type) {
                "imu" -> engine.feedImu(e.t, e.ax, e.ay, e.az, e.gx, e.gy, e.gz)
                "gnss" -> if (!withholdGnss) engine.feedGnss(e.t, e.lat, e.lon, e.alt, e.speed, e.hdop, e.sats)
                "outage" -> {
                    withholdGnss = e.outage || e.type == "outage" && e.outage
                    onOutage(withholdGnss)
                }
            }
        }
    }
}

/** Host-side e2e: constant-velocity DR when GNSS withheld. */
class FakeEnginePort : EnginePort {
    private var initOk = false
    var lastLat = 12.9716
    var lastLon = 77.5946
    private var estLat = 12.9716
    private var estLon = 77.5946
    private var lastT = 0.0
    private var haveT = false
    private var gnssHeld = false
    var gnssFeeds = 0
        private set
    var imuFeeds = 0
        private set

    fun setHoldGnss(hold: Boolean) { gnssHeld = hold }

    override fun init(mapPath: String, onnxPath: String): Boolean {
        initOk = true
        return true
    }
    override fun shutdown() { initOk = false }
    override fun feedImu(t: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double) {
        imuFeeds++
        if (gnssHeld && haveT) {
            val dt = (t - lastT).coerceIn(0.0, 0.05)
            val m = 12.0 * dt
            estLat += (m / 111320.0)
        }
        lastT = t
        haveT = true
    }
    override fun feedGnss(t: Double, lat: Double, lon: Double, alt: Double, speedMps: Double, hdop: Double, sats: Int) {
        if (gnssHeld) return
        gnssFeeds++
        lastLat = lat
        lastLon = lon
        estLat = lat
        estLon = lon
        lastT = t
        haveT = true
    }
    override fun poll(): NavSnapshot? {
        if (!initOk) return null
        return NavSnapshot(lastT, estLat, estLon, 0.0, 12.0, gnssHeld, 0.8, true, "",
            "in_region", true, "fake", 1, "mock")
    }
    override fun selectMap(lat: Double, lon: Double) = true
    override fun mapCovers(lat: Double, lon: Double) = true
    override fun diagnostics() = EngineDiagnostics()
    override fun lastError() = ""
    override fun isInitialized() = initOk
}
