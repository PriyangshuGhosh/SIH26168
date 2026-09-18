package com.example.member6app.camera

import android.util.Log

/**
 * VisionAdapter — Interface between the vision pipeline and the EKF fusion engine.
 *
 * INTEGRATION STATUS: PENDING MEMBER 3 API
 *
 * The correct architecture is:
 *   Camera → VisionPipeline → VisionAdapter → Member 3 EKF → Navigation State
 *
 * Member 3 (EKFFusionEngine) does NOT currently expose a visual-measurement
 * update API. Until it does, this adapter:
 *   1. Receives vision results from the camera pipeline.
 *   2. Evaluates the confidence gate.
 *   3. LOGS what it would inject (for verification).
 *   4. Does NOT modify EKF state directly.
 *   5. Does NOT fabricate "VISION ASSISTED" navigation.
 *
 * When Member 3 adds updateVisualMeasurement(), integrate here:
 *   // TODO-MEMBER3: ekf.updateVisualMeasurement(visualMeasurement)
 *
 * Confidence policy:
 *   GOOD     (≥ 0.7): Would inject measurement with full covariance.
 *   DEGRADED (≥ 0.4): Would inject with inflated covariance (down-weighted).
 *   BAD      (< 0.4): Reject — do not feed EKF.
 */
class VisionAdapter {

    companion object {
        private const val TAG         = "VisionAdapter"
        private const val GATE_GOOD   = 0.7
        private const val GATE_DEGRADE = 0.4
    }

    // The last vision result passed to the adapter
    private var lastResult: VisionResult? = null

    /**
     * Process a VisionResult. Applies confidence gating.
     *
     * @return VisionGatedOutput describing the gate decision.
     */
    fun onVisionResult(result: VisionResult): VisionGatedOutput {
        lastResult = result

        return when {
            result.confidence >= GATE_GOOD -> {
                Log.v(TAG, "GOOD (conf=${result.confidence}) — PENDING MEMBER3 integration")
                // TODO-MEMBER3: ekf.updateVisualMeasurement(buildMeasurement(result, covScale=1.0))
                VisionGatedOutput(
                    decision    = VisionDecision.GOOD,
                    confidence  = result.confidence,
                    injected    = false,    // Not yet — pending Member 3
                    reason      = "GOOD — EKF integration pending Member 3 API"
                )
            }
            result.confidence >= GATE_DEGRADE -> {
                Log.v(TAG, "DEGRADED (conf=${result.confidence}) — would down-weight")
                // TODO-MEMBER3: ekf.updateVisualMeasurement(buildMeasurement(result, covScale=4.0))
                VisionGatedOutput(
                    decision    = VisionDecision.DEGRADED,
                    confidence  = result.confidence,
                    injected    = false,
                    reason      = "DEGRADED — EKF integration pending Member 3 API"
                )
            }
            else -> {
                Log.v(TAG, "BAD (conf=${result.confidence} status=${result.status}) — rejected")
                VisionGatedOutput(
                    decision    = VisionDecision.BAD,
                    confidence  = result.confidence,
                    injected    = false,
                    reason      = "BAD — rejected (${result.status})"
                )
            }
        }
    }

    fun lastVisionStatus(): String = lastResult?.status ?: "NO_FRAME"
    fun lastVisionConfidence(): Double = lastResult?.confidence ?: 0.0
}

enum class VisionDecision { GOOD, DEGRADED, BAD }

data class VisionGatedOutput(
    val decision:   VisionDecision,
    val confidence: Double,
    val injected:   Boolean,
    val reason:     String
)
