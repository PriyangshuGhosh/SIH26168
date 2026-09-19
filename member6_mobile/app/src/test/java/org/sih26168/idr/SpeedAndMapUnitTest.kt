package org.sih26168.idr

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SpeedAndMapUnitTest {
    @Test
    fun unitsAreUnambiguous() {
        assertEquals(36.0, SpeedUnits.mpsToKmh(10.0), 1e-12)
        assertEquals(10.0, SpeedUnits.kmhToMps(36.0), 1e-12)
        assertEquals("Speed unavailable", SpeedDisplay.formatKmh(194.4, true))
        assertEquals("Speed unavailable", SpeedDisplay.formatKmh(10.0, false))
        assertTrue(SpeedDisplay.formatKmh(10.0, true).contains("36"))
    }

    @Test
    fun catalogSelectsByBoundsNotCityName() {
        val json = """
            {"regions":[{"id":"synthetic_grid_demo","roadpack":"synthetic_grid.roadpack",
            "min_lat":12.9715,"max_lat":12.9738,"min_lon":77.5945,"max_lon":77.5969}]}
        """.trimIndent()
        val regions = MapCatalogParser.parse(json)
        assertEquals(1, regions.size)
        assertTrue(regions[0].contains(12.9716, 77.5946))
        assertFalse(regions[0].contains(17.6868, 83.2185))
        assertFalse(regions[0].contains(28.6139, 77.2090))
    }

    @Test
    fun imuPairerRequiresTimestampSkew() {
        val p = ImuSamplePairer(0.008)
        assertEquals(null, p.feedAccelNs(1_000_000_000L, 0.1, 0.0, 9.81))
        val s = p.feedGyroNs(1_003_000_000L, 0.0, 0.0, 0.01)
        assertTrue(s != null)
        assertEquals(0.1, s!!.ax, 1e-9)
        assertEquals(null, p.feedGyroNs(1_050_000_000L, 0.0, 0.0, 0.0))
    }
}
