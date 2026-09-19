package org.sih26168.idr

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

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

class OutageAndReplayTest {
    @Test
    fun geodesicKnownShortBaseline() {
        val m = Geodesic.haversineMeters(12.9716, 77.5946, 12.9716, 77.5956)
        assertTrue(m in 100.0..120.0)
    }

    @Test
    fun finalDriftIsEstimatedAtRestoreVsRestoredGps() {
        val tr = OutageTracker()
        tr.noteRawGps(0.0, 12.9716, 77.5946, feedToEngine = true)
        tr.noteEstimate(1.0, 12.9716, 77.5946, deadReckoning = true, simulatedOutage = true)
        tr.noteEstimate(5.0, 12.9730, 77.5946, deadReckoning = true, simulatedOutage = true)
        tr.noteEstimate(6.0, 12.9730, 77.5946, deadReckoning = false, simulatedOutage = false)
        val rec = tr.noteRawGps(6.1, 12.9717, 77.5946, feedToEngine = true)
        assertTrue(rec != null)
        val expected = Geodesic.haversineMeters(12.9730, 77.5946, 12.9717, 77.5946)
        assertEquals(expected, rec!!.finalDriftMeters, 1e-6)
        val gpsGap = rec.gpsDisplacementDuringOutageMeters!!
        val lastGpsVsNew = Geodesic.haversineMeters(12.9716, 77.5946, 12.9717, 77.5946)
        assertEquals(lastGpsVsNew, gpsGap, 1e-6)
        assertTrue(abs(rec.finalDriftMeters - gpsGap) > 50.0)
    }

    @Test
    fun replayE2eFakeEngineHoldsGnss() {
        val engine = FakeEnginePort()
        engine.init("mock", "mock")
        val tracker = OutageTracker()
        val events = ReplayParser.parseJsonl(
            """
            {"type":"gnss","t":0.0,"lat":12.9716,"lon":77.5946,"speed":12,"hdop":1,"sats":10}
            {"type":"imu","t":0.2,"ax":0,"ay":0,"az":9.81,"gx":0,"gy":0,"gz":0}
            {"type":"outage","t":1.0,"active":true}
            {"type":"imu","t":1.2,"ax":0,"ay":0,"az":9.81,"gx":0,"gy":0,"gz":0}
            {"type":"imu","t":2.2,"ax":0,"ay":0,"az":9.81,"gx":0,"gy":0,"gz":0}
            {"type":"outage","t":3.0,"active":false}
            {"type":"gnss","t":3.0,"lat":12.9719,"lon":77.5946,"speed":12,"hdop":1,"sats":10}
            """.trimIndent()
        )
        var hold = false
        engine.feedGnss(0.0, 12.9716, 77.5946, 0.0, 12.0, 1.0, 10)
        tracker.noteRawGps(0.0, 12.9716, 77.5946, true)
        for (e in events) {
            when (e.type) {
                "outage" -> {
                    hold = e.outage
                    engine.setHoldGnss(hold)
                    if (!hold) {
                        val snap = engine.poll()!!
                        tracker.noteEstimate(snap.timestamp, snap.lat, snap.lon, true, false)
                    }
                }
                "imu" -> {
                    engine.feedImu(e.t, e.ax, e.ay, e.az, e.gx, e.gy, e.gz)
                    val snap = engine.poll()!!
                    tracker.noteEstimate(snap.timestamp, snap.lat, snap.lon, hold, hold)
                }
                "gnss" -> {
                    engine.feedGnss(e.t, e.lat, e.lon, e.alt, e.speed, e.hdop, e.sats)
                    tracker.noteRawGps(e.t, e.lat, e.lon, !hold)
                }
            }
        }
        assertTrue(tracker.history.isNotEmpty())
        val rec = tracker.history.last()
        assertTrue(rec.finalDriftMeters.isFinite())
        assertTrue(engine.imuFeeds >= 2)
    }

    @Test
    fun navModeExplicit() {
        val m = NavModeResolver.resolve(null, true, false, false, true, true, null, false)
        assertEquals(NavigationMode.SIMULATED_OUTAGE, m)
        val map = NavModeResolver.resolve(null, true, false, false, false, true, null, true)
        assertEquals(NavigationMode.MAP_UNAVAILABLE, map)
    }

    @Test
    fun roadpackParserReadsHeader() {
        val text = """
            SIH26168_ROADPACK_V1
            NUM_NODES 2
            NODE 0 12.97160000 77.59460000
            NODE 1 12.97160000 77.59500000
            NUM_SEGMENTS 1
            SEG 1 0 1 40.0 1.57 2
            LABEL test
            PT 12.97160000 77.59460000
            PT 12.97160000 77.59500000
        """.trimIndent()
        val g = RoadpackParser.parse(text)!!
        assertEquals(1, g.polylines.size)
        assertEquals(2, g.polylines[0].points.size)
    }
}
