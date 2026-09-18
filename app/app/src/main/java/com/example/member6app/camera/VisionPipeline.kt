package com.example.member6app.camera

import android.graphics.ImageFormat
import android.util.Log
import androidx.camera.core.ImageProxy
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.sqrt

/**
 * VisionPipeline — Lightweight visual confidence estimator.
 *
 * STATUS: EXPERIMENTAL / AUXILIARY
 *
 * This pipeline does NOT perform full visual odometry. It computes a
 * confidence score from image quality signals that would gate any future
 * visual measurement before it enters the EKF.
 *
 * Signals used:
 *   1. Frame variance (blur / texture proxy)
 *   2. Mean brightness (over/under-exposure)
 *   3. Inter-frame mean absolute difference (motion magnitude)
 *
 * Output: VisionResult.confidence in [0, 1]
 *   >= 0.7  → GOOD  (visual measurement could be trusted)
 *   >= 0.4  → DEGRADED (down-weight or hold)
 *   <  0.4  → BAD   (reject)
 *
 * Vision/EKF integration status:
 *   Member 3 does NOT yet expose a visual-measurement API.
 *   This pipeline produces confidence but does NOT inject data into the EKF.
 *   Integration point is clearly documented in VisionAdapter.kt.
 *
 * Failure handling:
 *   Any exception returns confidence = 0.0, status = "VISION_ERROR".
 *   Baseline navigation (IMU+GNSS+Member5) is unaffected.
 */
class VisionPipeline {

    companion object {
        private const val TAG        = "VisionPipeline"
        private const val SUBSAMPLE  = 8      // process every 8th pixel for speed
        private const val BLUR_THR   = 200.0  // variance below this → blurry
        private const val BRIGHT_MIN = 30.0   // mean luma below → dark
        private const val BRIGHT_MAX = 220.0  // mean luma above → overexposed
        private const val MOTION_MIN = 2.0    // MAD below → stationary / no texture
        private const val MOTION_MAX = 80.0   // MAD above → excessive shake
    }

    private var prevLumaData: DoubleArray? = null
    private var prevWidth  = 0
    private var prevHeight = 0

    fun process(imageProxy: ImageProxy, timestampSeconds: Double): VisionResult {
        val t0 = System.currentTimeMillis()
        return try {
            val plane = imageProxy.planes[0]  // Y plane (luma) of YUV_420_888
            val buffer = plane.buffer
            val rowStride = plane.rowStride
            val width  = imageProxy.width
            val height = imageProxy.height

            // Extract subsampled luma array
            val lumas = extractSubsampledLuma(buffer.array(), rowStride, width, height)

            // Signal 1: mean brightness
            val meanBright = lumas.average()

            // Signal 2: variance (blur proxy)
            val variance = computeVariance(lumas, meanBright)

            // Signal 3: inter-frame MAD
            val mad = if (prevLumaData != null && prevWidth == width && prevHeight == height) {
                computeMAD(lumas, prevLumaData!!)
            } else 10.0  // unknown on first frame — neutral

            // Store current frame for next diff
            prevLumaData = lumas.copyOf()
            prevWidth  = width
            prevHeight = height

            // Score each signal in [0, 1]
            val brightScore = brightScore(meanBright)
            val blurScore   = blurScore(variance)
            val motionScore = motionScore(mad)

            // Weighted combination
            val confidence = (0.4 * blurScore + 0.35 * brightScore + 0.25 * motionScore)
                .coerceIn(0.0, 1.0)

            val status = when {
                confidence >= 0.7 -> "GOOD"
                confidence >= 0.4 -> "DEGRADED"
                else              -> "BAD"
            }

            val processingMs = System.currentTimeMillis() - t0
            Log.v(TAG, "Vision: conf=%.2f bright=%.1f var=%.1f mad=%.1f → $status (${processingMs}ms)"
                .format(confidence, meanBright, variance, mad))

            VisionResult(
                timestamp      = timestampSeconds,
                confidence     = confidence,
                status         = status,
                meanBrightness = meanBright,
                variance       = variance,
                interFrameMAD  = mad,
                processingMs   = processingMs
            )
        } catch (e: Exception) {
            Log.e(TAG, "Vision pipeline failed: ${e.message}")
            VisionResult(
                timestamp  = timestampSeconds,
                confidence = 0.0,
                status     = "VISION_ERROR",
                processingMs = System.currentTimeMillis() - t0
            )
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private fun extractSubsampledLuma(data: ByteArray, rowStride: Int, width: Int, height: Int): DoubleArray {
        val result = mutableListOf<Double>()
        var row = 0
        while (row < height) {
            var col = 0
            while (col < width) {
                val idx = row * rowStride + col
                if (idx < data.size) {
                    result.add((data[idx].toInt() and 0xFF).toDouble())
                }
                col += SUBSAMPLE
            }
            row += SUBSAMPLE
        }
        return result.toDoubleArray()
    }

    private fun computeVariance(lumas: DoubleArray, mean: Double): Double {
        if (lumas.isEmpty()) return 0.0
        return lumas.sumOf { (it - mean) * (it - mean) } / lumas.size
    }

    private fun computeMAD(current: DoubleArray, prev: DoubleArray): Double {
        val n = min(current.size, prev.size)
        if (n == 0) return 0.0
        return (0 until n).sumOf { abs(current[it] - prev[it]) } / n
    }

    private fun brightScore(mean: Double) = when {
        mean < BRIGHT_MIN -> (mean / BRIGHT_MIN).coerceIn(0.0, 1.0)
        mean > BRIGHT_MAX -> ((255.0 - mean) / (255.0 - BRIGHT_MAX)).coerceIn(0.0, 1.0)
        else -> 1.0
    }

    private fun blurScore(variance: Double) = (variance / BLUR_THR).coerceIn(0.0, 1.0)

    private fun motionScore(mad: Double) = when {
        mad < MOTION_MIN -> (mad / MOTION_MIN).coerceIn(0.0, 1.0) * 0.5
        mad > MOTION_MAX -> (1.0 - (mad - MOTION_MAX) / MOTION_MAX).coerceIn(0.0, 1.0)
        else -> 1.0
    }
}

data class VisionResult(
    val timestamp: Double      = 0.0,
    val confidence: Double     = 0.0,
    val status: String         = "UNINIT",
    val meanBrightness: Double = 0.0,
    val variance: Double       = 0.0,
    val interFrameMAD: Double  = 0.0,
    val processingMs: Long     = 0L
)
