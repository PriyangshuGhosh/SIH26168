package org.sih26168.idr

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.concurrent.thread
import kotlin.math.abs

/** drift_m = geodesic(estimate at GNSS restore, restored GNSS fix). Nothing else. */
class OutageDriftTest {
    private val lon = 77.5946

    @Test
    fun geodesicScaleAndArgumentOrder() {
        // 1 degree of latitude on the equator with R = 6378137 m.
        assertEquals(111_319.49, Geodesic.haversineMeters(0.0, 0.0, 1.0, 0.0), 0.5)
        // 0.001 deg lat ~ 111.3 m; 0.001 deg lon at 12.97N ~ 108.5 m (lat/lon are not interchangeable).
        assertEquals(111.32, Geodesic.haversineMeters(12.9716, lon, 12.9726, lon), 0.05)
        assertEquals(108.48, Geodesic.haversineMeters(12.9716, lon, 12.9716, lon + 0.001), 0.05)
        assertEquals(0.0, Geodesic.haversineMeters(12.9716, lon, 12.9716, lon), 0.0)
        assertTrue(Geodesic.haversineMeters(Double.NaN, lon, 12.9716, lon).isNaN())
    }

    @Test
    fun driftUsesEstimateSampledBeforeFeedNotPostFeedPoll() {
        val tr = OutageTracker()
        tr.noteRawGps(0.0, 12.9716, lon, feedToEngine = true)
        tr.noteEstimate(1.0, 12.9716, lon, deadReckoning = true, simulatedOutage = false)
        tr.noteEstimate(5.0, 12.9730, lon, deadReckoning = true, simulatedOutage = false)
        // Race: engine already snapped to the restored fix and a poll saw it before noteRawGps ran.
        tr.noteEstimate(5.05, 12.9717, lon, deadReckoning = false, simulatedOutage = false)

        val preFeed = GeoPoint(5.0, 12.9730, lon)
        val rec = tr.noteRawGps(5.1, 12.9717, lon, feedToEngine = true, estimateAtRestore = preFeed)!!

        assertEquals(144.715, rec.finalDriftMeters, 0.01)
        assertEquals(preFeed, rec.estimatedAtRestore)
        assertEquals(12.9717, rec.restoredGps.lat, 0.0)
    }

    @Test
    fun driftIsNotDurationTravelOrLastGpsDistance() {
        val tr = OutageTracker()
        tr.noteRawGps(100.0, 12.9716, lon, feedToEngine = true)
        // Long outage (200 s), ~890 m travelled, but the estimate ends 11.13 m from the restored fix.
        var lat = 12.9716
        var t = 101.0
        while (t < 300.0) {
            tr.noteEstimate(t, lat, lon, deadReckoning = true, simulatedOutage = false)
            lat += 0.00004
            t += 1.0
        }
        val estLat = 12.9717
        tr.noteEstimate(300.0, estLat, lon, deadReckoning = true, simulatedOutage = false)
        val rec = tr.noteRawGps(300.1, 12.9716, lon, feedToEngine = true,
            estimateAtRestore = GeoPoint(300.0, estLat, lon))!!

        assertEquals(11.13, rec.finalDriftMeters, 0.01)
        assertTrue(rec.durationS > 190.0)
        assertTrue(abs(rec.finalDriftMeters - rec.durationS) > 100.0)
        val travelled = Geodesic.haversineMeters(12.9716, lon, 12.9716 + 0.00004 * 199, lon)
        assertTrue(abs(rec.finalDriftMeters - travelled) > 500.0)
        assertEquals(12.9716, rec.lastGpsBeforeOutage!!.lat, 0.0)
        assertEquals(100.0, rec.lastGpsBeforeOutage!!.t, 0.0)
    }

    @Test
    fun noRecordWhileGpsIsNotFedAndNoInventedZeroDrift() {
        val tr = OutageTracker()
        tr.noteRawGps(0.0, 12.9716, lon, feedToEngine = true)
        tr.noteEstimate(1.0, 12.9716, lon, deadReckoning = false, simulatedOutage = true)
        // Real GPS keeps arriving during a SIMULATED cut but is not fed: no restore yet.
        assertNull(tr.noteRawGps(2.0, 12.9720, lon, feedToEngine = false))
        assertTrue(tr.inOutage)
        assertTrue(tr.history.isEmpty())
        // Last valid GNSS must stay the pre-outage fix, not the withheld one.
        assertEquals(12.9716, tr.lastGps!!.lat, 0.0)
        // Non-finite fixes are ignored, never recorded.
        assertNull(tr.noteRawGps(3.0, Double.NaN, lon, feedToEngine = true))
        assertTrue(tr.inOutage)
        val rec = tr.noteRawGps(4.0, 12.9720, lon, feedToEngine = true,
            estimateAtRestore = GeoPoint(3.9, 12.9716, lon))
        assertNotNull(rec)
        assertTrue(rec!!.simulated)
        assertEquals(44.53, rec.finalDriftMeters, 0.05)
        assertFalse(tr.inOutage)
    }

    @Test
    fun trackerSurvivesConcurrentPollAndGpsCallbacks() {
        val tr = OutageTracker()
        tr.noteRawGps(0.0, 12.9716, lon, feedToEngine = true)
        var failure: Throwable? = null
        val poller = thread {
            try {
                for (i in 1..20_000) {
                    tr.noteEstimate(i * 0.01, 12.9716 + i * 1e-7, lon, deadReckoning = i % 300 < 200, simulatedOutage = false)
                    tr.liveTrail; tr.liveDurationS; tr.history
                }
            } catch (e: Throwable) { failure = e }
        }
        val gps = thread {
            try {
                for (i in 1..2_000) {
                    tr.noteRawGps(i * 0.1, 12.9716, lon, feedToEngine = true,
                        estimateAtRestore = GeoPoint(i * 0.1, 12.9717, lon))
                }
            } catch (e: Throwable) { failure = e }
        }
        poller.join(); gps.join()
        assertNull(failure)
        assertTrue(tr.history.all { it.finalDriftMeters.isFinite() })
    }
}
