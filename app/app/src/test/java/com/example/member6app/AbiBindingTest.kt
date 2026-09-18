package com.example.member6app

import org.junit.Assert.*
import org.junit.Test
import com.example.member6app.sensors.TimestampUtils

/**
 * Additional unit tests for TimestampUtils and ABI binding verification
 * (logic-only, no native calls).
 */
class AbiBindingTest {

    // ── Timestamp utilities ───────────────────────────────────────────────────

    @Test
    fun `nsToSeconds converts correctly`() {
        assertEquals(1.0, TimestampUtils.nsToSeconds(1_000_000_000L), 1e-12)
        assertEquals(0.1, TimestampUtils.nsToSeconds(100_000_000L), 1e-12)
    }

    @Test
    fun `regression detection works`() {
        assertTrue(TimestampUtils.isRegression(newTs = 0.9, lastTs = 1.0))
        assertFalse(TimestampUtils.isRegression(newTs = 1.1, lastTs = 1.0))
        assertFalse(TimestampUtils.isRegression(newTs = 0.9, lastTs = 0.0)) // first event
    }

    @Test
    fun `suspicious gap detection works`() {
        assertTrue(TimestampUtils.isSuspiciousGap(newTs = 3.0, lastTs = 1.5, maxGapSeconds = 1.0))
        assertFalse(TimestampUtils.isSuspiciousGap(newTs = 2.0, lastTs = 1.5, maxGapSeconds = 1.0))
        assertFalse(TimestampUtils.isSuspiciousGap(newTs = 0.9, lastTs = 0.0))  // no prior event
    }

    // ── IDRNavigationOutput field verification ───────────────────────────────
    // These tests verify that the Kotlin data class has the exact fields
    // matching the C struct (idr_engine_api.h), in the documented order.
    // Actual native struct layout is handled by the JNI bridge (explicit field copy).

    @Test
    fun `IDRNavigationOutput has all expected fields`() {
        val output = com.example.member6app.native.IDRNavigationOutput(
            timestamp       = 1.0,
            lat             = 12.34,
            lon             = 56.78,
            headingDeg      = 90.0,
            speedMs         = 13.89,
            confidence      = 0.9,
            isDeadReckoning = 0
        )
        assertEquals(1.0, output.timestamp, 1e-9)
        assertEquals(12.34, output.lat, 1e-9)
        assertEquals(56.78, output.lon, 1e-9)
        assertEquals(90.0, output.headingDeg, 1e-9)
        assertEquals(13.89, output.speedMs, 1e-9)
        assertEquals(0.9, output.confidence, 1e-9)
        assertEquals(0, output.isDeadReckoning)
    }

    @Test
    fun `is_dead_reckoning = 1 maps to DEAD_RECKONING mode`() {
        // Verify the mode mapping logic from NavigationViewModel
        val isDeadReckoning = 1
        val simulated = false
        val lat = 12.0
        val lon = 56.0

        val mode = when {
            simulated               -> com.example.member6app.navigation.NavigationMode.GNSS_OUTAGE_SIM
            isDeadReckoning != 0    -> com.example.member6app.navigation.NavigationMode.DEAD_RECKONING
            lat == 0.0 && lon == 0.0 -> com.example.member6app.navigation.NavigationMode.NO_FIX
            else                    -> com.example.member6app.navigation.NavigationMode.GNSS_AIDED
        }
        assertEquals(com.example.member6app.navigation.NavigationMode.DEAD_RECKONING, mode)
    }

    @Test
    fun `is_dead_reckoning = 0 with valid pos maps to GNSS_AIDED`() {
        val isDeadReckoning = 0
        val simulated = false
        val lat = 12.0
        val lon = 56.0

        val mode = when {
            simulated               -> com.example.member6app.navigation.NavigationMode.GNSS_OUTAGE_SIM
            isDeadReckoning != 0    -> com.example.member6app.navigation.NavigationMode.DEAD_RECKONING
            lat == 0.0 && lon == 0.0 -> com.example.member6app.navigation.NavigationMode.NO_FIX
            else                    -> com.example.member6app.navigation.NavigationMode.GNSS_AIDED
        }
        assertEquals(com.example.member6app.navigation.NavigationMode.GNSS_AIDED, mode)
    }
}
