package com.example.member6app

import org.junit.Assert.assertEquals
import org.junit.Test

class SpeedDisplayTest {
    @Test
    fun invalidSpeedIsUnavailable() {
        assertEquals("Speed unavailable", SpeedDisplay.formatKmh(194.4, true))
        assertEquals("Speed unavailable", SpeedDisplay.formatKmh(10.0, false))
        assertEquals("Speed unavailable", SpeedDisplay.formatKmh(Double.NaN, true))
    }

    @Test
    fun validSpeedUsesCanonicalConversion() {
        assertEquals("36.0 km/h", SpeedDisplay.formatKmh(10.0, true))
    }
}
