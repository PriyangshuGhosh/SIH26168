package com.vizag.nav

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.util.Log
import java.nio.FloatBuffer

/**
 * Wraps the ONNX Runtime Android session for `final.production.onnx`.
 *
 * Model contract (from repo member1-ml):
 *   Input:  "imu_window_100hz"  shape [1, 200, 6]  Float32
 *   Output: "velocity_mps"      shape [1]           Float32  (m/s, clamped >= 0)
 *           "velocity_variance_m2s2" shape [1]      Float32
 *           "confidence"        shape [1]           Float32  (0..1)
 */
class OnnxInference(context: Context) {

    companion object {
        private const val TAG = "OnnxInference"
        private const val MODEL_ASSET = "final.production.onnx"
        private const val INPUT_NAME  = "imu_window_100hz"
        private const val OUT_SPEED   = "velocity_mps"
        private const val OUT_VAR     = "velocity_variance_m2s2"
        private const val OUT_CONF    = "confidence"
    }

    data class Result(
        val velocityMps: Float,
        val varianceM2s2: Float,
        val confidence: Float
    ) {
        val speedKmh: Float get() = velocityMps * 3.6f
    }

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private var session: OrtSession? = null
    private var hasVarianceOutputs = true

    val isReady: Boolean get() = session != null

    init {
        try {
            val modelBytes = context.assets.open(MODEL_ASSET).readBytes()
            val opts = OrtSession.SessionOptions().apply {
                setIntraOpNumThreads(2)
                setInterOpNumThreads(1)
            }
            session = env.createSession(modelBytes, opts)
            Log.i(TAG, "ONNX session ready. Inputs: ${session?.inputNames} Outputs: ${session?.outputNames}")
            // Check if model has the 3-output uncertainty variant
            hasVarianceOutputs = session?.outputNames?.containsAll(listOf(OUT_VAR, OUT_CONF)) == true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load ONNX model: ${e.message}", e)
        }
    }

    /**
     * Run inference on a [200 * 6] flat FloatArray in chronological row-major order.
     * Returns null if session is unavailable or inference fails.
     */
    fun predict(window200x6: FloatArray): Result? {
        val sess = session ?: return null
        return try {
            // Shape: [1, 200, 6]  — batch=1, timesteps=200, channels=6
            val shape = longArrayOf(1L, 200L, 6L)
            val buf = FloatBuffer.wrap(window200x6)
            val tensor = OnnxTensor.createTensor(env, buf, shape)
            val inputs = mapOf(INPUT_NAME to tensor)
            val outputs = sess.run(inputs)

            
            val speedTensor = outputs[OUT_SPEED].get()
            val speedVal = speedTensor.value
            val vMps = (if (speedVal is FloatArray) speedVal[0] 
                       else if (speedVal is Array<*>) (speedVal[0] as FloatArray)[0] 
                       else 0f).coerceAtLeast(0f)

            var variance = 0f
            var conf     = 1f
            if (hasVarianceOutputs) {
                try {
                    val varVal = outputs[OUT_VAR].get().value
                    variance = if (varVal is FloatArray) varVal[0] else if (varVal is Array<*>) (varVal[0] as FloatArray)[0] else 0f
                    
                    val confVal = outputs[OUT_CONF].get().value
                    conf = if (confVal is FloatArray) confVal[0] else if (confVal is Array<*>) (confVal[0] as FloatArray)[0] else 1f
                } catch (_: Exception) { /* graceful fallback */ }
            }

            tensor.close(); outputs.close()
            Result(vMps, variance, conf)
        } catch (e: Exception) {
            Log.e(TAG, "Inference error: ${e.message}", e)
            null
        }
    }

    fun close() {
        session?.close()
        session = null
    }
}
