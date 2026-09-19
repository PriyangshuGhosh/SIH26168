package org.sih26168.idr

import java.io.File

data class MapRegionInfo(
    val regionId: String,
    val minLatitude: Double,
    val maxLatitude: Double,
    val minLongitude: Double,
    val maxLongitude: Double,
    val roadpackPath: String,
    val version: String,
    val source: String,
    val checksum: String,
    val bytes: Long,
    val synthetic: Boolean,
    val edgeCount: Int
) {
    fun contains(lat: Double, lon: Double): Boolean =
        lat.isFinite() && lon.isFinite() &&
            lat >= minLatitude && lat <= maxLatitude &&
            lon >= minLongitude && lon <= maxLongitude

    fun areaDeg2(): Double =
        (maxLatitude - minLatitude).coerceAtLeast(0.0) * (maxLongitude - minLongitude).coerceAtLeast(0.0)

    fun signedDistanceToBoundaryM(lat: Double, lon: Double): Double {
        val dLatN = (maxLatitude - lat) * 111320.0
        val dLatS = (lat - minLatitude) * 111320.0
        val cos = kotlin.math.cos(Math.toRadians(lat)).coerceAtLeast(1e-6)
        val dLonE = (maxLongitude - lon) * 111320.0 * cos
        val dLonW = (lon - minLongitude) * 111320.0 * cos
        if (!contains(lat, lon)) return -minOf(kotlin.math.abs(dLatN), kotlin.math.abs(dLatS), kotlin.math.abs(dLonE), kotlin.math.abs(dLonW))
        return minOf(dLatN, dLatS, dLonE, dLonW)
    }
}

data class StorageInfo(
    val usedBytes: Long,
    val maxBytes: Long,
    val remainingBytes: Long,
    val regionCount: Int,
    val activeRegionId: String?
)

data class DownloadStateInfo(val regionId: String, val state: String, val error: String, val progress: Float)

/** Local catalog only. No Google tiles. Live OSM fetch is host-side (Member 4). */
class LocalRoadDataManager(
    private val catalogRoot: File,
    private val maxBytes: Long = 64L * 1024L * 1024L
) {
    var activeRegionId: String? = null
        private set

    fun getAvailableRegions(): List<MapRegionInfo> {
        val manifest = File(catalogRoot, "manifest.json")
        if (!manifest.isFile) return emptyList()
        return MapCatalogParser.parse(manifest.readText()).map { r ->
            val pack = resolve(r.roadpackRelative)
            MapRegionInfo(
                regionId = r.id,
                minLatitude = r.minLat,
                maxLatitude = r.maxLat,
                minLongitude = r.minLon,
                maxLongitude = r.maxLon,
                roadpackPath = pack.absolutePath,
                version = "1",
                source = if (r.id.startsWith("synthetic")) "synthetic" else "OpenStreetMap",
                checksum = "",
                bytes = if (pack.isFile) pack.length() else 0L,
                synthetic = r.id.startsWith("synthetic"),
                edgeCount = 0
            )
        }
    }

    fun getActiveRegion(): MapRegionInfo? =
        getAvailableRegions().firstOrNull { it.regionId == activeRegionId }

    fun isRegionAvailable(lat: Double, lon: Double): Boolean = findCovering(lat, lon) != null

    fun findCovering(lat: Double, lon: Double): MapRegionInfo? {
        val hits = getAvailableRegions().filter { it.contains(lat, lon) }
        return hits.minByOrNull { it.areaDeg2() }
    }

    fun selectForLocation(lat: Double, lon: Double): MapRegionInfo? {
        val hit = findCovering(lat, lon)
        activeRegionId = hit?.regionId
        return hit
    }

    fun approachingBoundary(lat: Double, lon: Double, thresholdM: Double): Boolean {
        val active = getActiveRegion() ?: return false
        val d = active.signedDistanceToBoundaryM(lat, lon)
        return d >= 0.0 && d <= thresholdM
    }

    fun storageInfo(): StorageInfo {
        val regions = getAvailableRegions()
        val used = regions.sumOf { it.bytes }
        return StorageInfo(used, maxBytes, (maxBytes - used).coerceAtLeast(0), regions.size, activeRegionId)
    }

    fun getDownloadState(regionId: String? = null): DownloadStateInfo {
        val id = regionId ?: activeRegionId ?: ""
        val ready = getAvailableRegions().any { it.regionId == id && File(it.roadpackPath).isFile }
        return DownloadStateInfo(id, if (ready) "ready" else "idle", "", if (ready) 1f else 0f)
    }

    private fun resolve(rel: String): File {
        val p = File(rel)
        return if (p.isAbsolute) p else File(catalogRoot, rel)
    }
}
