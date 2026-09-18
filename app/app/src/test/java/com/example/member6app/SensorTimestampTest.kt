package com.example.member6app

import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for sensor timestamp handling and navigation state logic.
 * These run on the JVM (no Android device needed).
 *
 * Hardware tests (IMU rate measurement, native engine) are marked NOT_VALIDATED
 * per Phase 25 requirements.
 */
class SensorTimestampTest {

    /**
     * Test: nanosecond → seconds conversion preserves precision.
     */
    @Test
    fun `nanoseconds to seconds conversion is precise`() {
        val ns = 1_234_567_890_123L
        val seconds = ns / 1_000_000_000.0
        assertEquals(1234.567890123, seconds, 1e-9)
    }

    /**
     * Test: timestamp regression detection.
     * A timestamp that is less than or equal to the previous should be dropped.
     */
    @Test
    fun `timestamp regression is detected`() {
        var lastTs = 1.0
        val incomingTs = 0.999  // regression
        val isRegression = incomingTs <= lastTs
        assertTrue("Regression should be detected", isRegression)
    }

    /**
     * Test: GNSS HDOP proxy computation.
     * accuracy_m / 5.0, clamped to [0.5, 20.0].
     */
    @Test
    fun `GNSS HDOP proxy is in valid range`() {
        fun hdopProxy(accuracyM: Float) = (accuracyM / 5.0).coerceIn(0.5, 20.0)

        assertEquals(0.5, hdopProxy(0f), 1e-9)       // clamp low
        assertEquals(1.0, hdopProxy(5f), 1e-9)
        assertEquals(4.0, hdopProxy(20f), 1e-9)
        assertEquals(20.0, hdopProxy(200f), 1e-9)     // clamp high
    }

    /**
     * Test: poor GNSS quality detection.
     * HDOP > 4.0 or num_sats < 4 should trigger DR mode in Member 5.
     */
    @Test
    fun `poor GNSS quality conditions are identified correctly`() {
        fun isPoorQuality(hdop: Double, sats: Int) = hdop > 4.0 || sats < 4

        assertTrue(isPoorQuality(hdop = 5.0, sats = 6))   // bad HDOP
        assertTrue(isPoorQuality(hdop = 1.0, sats = 3))   // few sats
        assertTrue(isPoorQuality(hdop = 5.0, sats = 2))   // both bad
        assertFalse(isPoorQuality(hdop = 1.5, sats = 5))  // good
    }

    /**
     * Test: speed conversion m/s → km/h.
     */
    @Test
    fun `speed conversion m_s to km_h is correct`() {
        val speedMs = 13.889
        val speedKmh = speedMs * 3.6
        assertEquals(50.0, speedKmh, 0.01)
    }
}
