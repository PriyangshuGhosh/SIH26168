package org.sih26168.idr

data class RoadPolyline(val id: Long, val points: List<Pair<Double, Double>>)

data class RoadpackGraph(
    val minLat: Double,
    val maxLat: Double,
    val minLon: Double,
    val maxLon: Double,
    val polylines: List<RoadPolyline>
)

object RoadpackParser {
    fun parse(text: String): RoadpackGraph? {
        val lines = text.lineSequence().toList()
        if (lines.isEmpty() || lines[0].trim() != "SIH26168_ROADPACK_V1") return null
        val polys = mutableListOf<RoadPolyline>()
        var minLat = Double.POSITIVE_INFINITY
        var maxLat = Double.NEGATIVE_INFINITY
        var minLon = Double.POSITIVE_INFINITY
        var maxLon = Double.NEGATIVE_INFINITY
        var i = 1
        while (i < lines.size) {
            val parts = lines[i].trim().split(Regex("\\s+"))
            if (parts.isEmpty() || parts[0] != "SEG" || parts.size < 7) {
                i++
                continue
            }
            val id = parts[1].toLongOrNull() ?: 0L
            val nPts = parts[6].toIntOrNull() ?: 0
            i++
            if (i < lines.size && lines[i].startsWith("LABEL ")) i++
            val pts = mutableListOf<Pair<Double, Double>>()
            while (i < lines.size && pts.size < nPts) {
                val p = lines[i].trim().split(Regex("\\s+"))
                i++
                if (p.isEmpty()) continue
                if (p[0] == "HIGHWAY" || p[0] == "MAXSPEED" || p[0] == "ONEWAY") continue
                if (p[0] != "PT" || p.size < 3) continue
                val lat = p[1].toDoubleOrNull() ?: continue
                val lon = p[2].toDoubleOrNull() ?: continue
                pts.add(lat to lon)
                minLat = minOf(minLat, lat); maxLat = maxOf(maxLat, lat)
                minLon = minOf(minLon, lon); maxLon = maxOf(maxLon, lon)
            }
            if (pts.size >= 2) polys.add(RoadPolyline(id, pts))
        }
        if (polys.isEmpty() || !minLat.isFinite()) return null
        return RoadpackGraph(minLat, maxLat, minLon, maxLon, polys)
    }
}
