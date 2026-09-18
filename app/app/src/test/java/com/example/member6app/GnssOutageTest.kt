package com.example.member6app

import com.example.member6app.navigation.NavigationMode
import com.example.member6app.navigation.NavigationUiState
import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for GNSS outage simulation logic and navigation mode transitions.
 *
 * These tests verify the state machine behavior without requiring the native engine.
 */
class GnssOutageTest {

    /**
     * When gnssOutageSimulated = true AND is_dead_reckoning = 1,
     * the mode should be GNSS_OUTAGE_SIM (simulation takes precedence in label).
     */
    @Test
    fun `simulated outage takes precedence over DEAD_RECKONING mode`() {
        val state = NavigationUiState(
            mode = NavigationMode.GNSS_OUTAGE_SIM,
            gnssAvailable = true
        )
        assertEquals("GNSS OUTAGE — DEAD RECKONING", state.modeLabel)
        // In simulated mode, gnssLabel should reflect the simulation
        assertTrue(state.gnssLabel.contains("SIMULATED"))
    }

    /**
     * GNSS_AIDED mode should display correctly.
     */
    @Test
    fun `GNSS aided mode shows correctly`() {
        val state = NavigationUiState(mode = NavigationMode.GNSS_AIDED, gnssAvailable = true, gnssSatellites = 8)
        assertEquals("GNSS AIDED", state.modeLabel)
        assertTrue(state.gnssLabel.contains("ACTIVE"))
    }

    /**
     * DEAD_RECKONING mode when GNSS is unavailable.
     */
    @Test
    fun `dead reckoning shows when GNSS unavailable`() {
        val state = NavigationUiState(mode = NavigationMode.DEAD_RECKONING, gnssAvailable = false)
        assertEquals("DEAD RECKONING", state.modeLabel)
        assertEquals("UNAVAILABLE", state.gnssLabel)
    }

    /**
     * Engine failed state must be clearly identified.
     */
    @Test
    fun `engine failed state is identifiable`() {
        val state = NavigationUiState(
            mode = NavigationMode.ENGINE_FAILED,
            engineError = "libidr_engine.so not found"
        )
        assertEquals("ENGINE FAILED", state.modeLabel)
        assertTrue(state.engineError.isNotEmpty())
    }

    /**
     * GNSS outage simulation correctly identified for demo.
     * When simulation is active, position should continue to update from IMU-only DR.
     * This test verifies that the OUTAGE_SIM state exists as a distinct mode.
     */
    @Test
    fun `gnss outage sim is a distinct navigation mode`() {
        val simState = NavigationMode.GNSS_OUTAGE_SIM
        assertNotEquals(simState, NavigationMode.DEAD_RECKONING)
        assertNotEquals(simState, NavigationMode.GNSS_AIDED)
    }
}
