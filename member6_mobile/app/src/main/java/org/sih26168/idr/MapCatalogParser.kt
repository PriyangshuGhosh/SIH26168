package org.sih26168.idr

data class MapRegion(
    val id: String,
    val roadpackRelative: String,
    val minLat: Double,
    val maxLat: Double,
    val minLon: Double,
    val maxLon: Double
) {
    fun contains(lat: Double, lon: Double): Boolean =
        lat.isFinite() && lon.isFinite() &&
            lat >= minLat && lat <= maxLat && lon >= minLon && lon <= maxLon
}

object MapCatalogParser {
    /**
     * Minimal parser for the SIH26168 maps/manifest.json schema.
     * Navigation logic never hardcodes a city name.
     */
    fun parse(json: String): List<MapRegion> {
        val regions = mutableListOf<MapRegion>()
        val arrStart = json.indexOf("\"regions\"")
        if (arrStart < 0) return regions
        val lb = json.indexOf('[', arrStart)
        val rb = json.lastIndexOf(']')
        if (lb < 0 || rb <= lb) return regions
        val body = json.substring(lb + 1, rb)
        var pos = 0
        while (true) {
            val o1 = body.indexOf('{', pos)
            if (o1 < 0) break
            val o2 = body.indexOf('}', o1)
            if (o2 < 0) break
            val obj = body.substring(o1, o2 + 1)
            val id = extractString(obj, "id") ?: continue
            val pack = extractString(obj, "roadpack") ?: continue
            val minLat = extractNumber(obj, "min_lat") ?: continue
            val maxLat = extractNumber(obj, "max_lat") ?: continue
            val minLon = extractNumber(obj, "min_lon") ?: continue
            val maxLon = extractNumber(obj, "max_lon") ?: continue
            regions.add(MapRegion(id, pack, minLat, maxLat, minLon, maxLon))
            pos = o2 + 1
        }
        return regions
    }

    private fun extractString(obj: String, key: String): String? {
        val p = obj.indexOf("\"$key\"")
        if (p < 0) return null
        val c = obj.indexOf(':', p)
        val q1 = obj.indexOf('"', c + 1)
        val q2 = obj.indexOf('"', q1 + 1)
        if (q1 < 0 || q2 < 0) return null
        return obj.substring(q1 + 1, q2)
    }

    private fun extractNumber(obj: String, key: String): Double? {
        val p = obj.indexOf("\"$key\"")
        if (p < 0) return null
        val c = obj.indexOf(':', p)
        val raw = obj.substring(c + 1).trim().takeWhile { it.isDigit() || it == '-' || it == '.' || it == 'e' || it == 'E' }
        return raw.toDoubleOrNull()
    }
}
