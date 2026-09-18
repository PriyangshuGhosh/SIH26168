package com.example.member6app

import com.example.member6app.camera.VisionPipeline
import com.example.member6app.camera.VisionAdapter
import com.example.member6app.camera.VisionResult
import com.example.member6app.camera.VisionDecision
import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for vision confidence gating and failure handling.
 *
 * These tests verify that:
 *   1. The confidence gate categorizes correctly (GOOD / DEGRADED / BAD).
 *   2. Vision failures (exception) return confidence = 0 / BAD.
 *   3. GOOD confidence does NOT claim EKF injection (pending Member 3).
 */
class VisionConfidenceTest {

    private val adapter = VisionAdapter()

    @Test
    fun `GOOD confidence is gated correctly`() {
        val result = VisionResult(confidence = 0.85, status = "GOOD")
        val output = adapter.onVisionResult(result)
        assertEquals(VisionDecision.GOOD, output.decision)
        assertFalse("EKF injection must be false — pending Member 3", output.injected)
    }

    @Test
    fun `DEGRADED confidence is gated correctly`() {
        val result = VisionResult(confidence = 0.55, status = "DEGRADED")
        val output = adapter.onVisionResult(result)
        assertEquals(VisionDecision.DEGRADED, output.decision)
        assertFalse(output.injected)
    }

    @Test
    fun `BAD confidence is rejected`() {
        val result = VisionResult(confidence = 0.20, status = "BAD")
        val output = adapter.onVisionResult(result)
        assertEquals(VisionDecision.BAD, output.decision)
        assertFalse(output.injected)
    }

    @Test
    fun `error confidence (0_0) is rejected`() {
        val result = VisionResult(confidence = 0.0, status = "VISION_ERROR")
        val output = adapter.onVisionResult(result)
        assertEquals(VisionDecision.BAD, output.decision)
    }

    @Test
    fun `confidence boundary at 0_7 is GOOD`() {
        val result = VisionResult(confidence = 0.70, status = "GOOD")
        val output = adapter.onVisionResult(result)
        assertEquals(VisionDecision.GOOD, output.decision)
    }

    @Test
    fun `confidence boundary at 0_4 is DEGRADED`() {
        val result = VisionResult(confidence = 0.40, status = "DEGRADED")
        val output = adapter.onVisionResult(result)
        assertEquals(VisionDecision.DEGRADED, output.decision)
    }

    @Test
    fun `confidence just below 0_4 is BAD`() {
        val result = VisionResult(confidence = 0.399, status = "BAD")
        val output = adapter.onVisionResult(result)
        assertEquals(VisionDecision.BAD, output.decision)
    }
}
