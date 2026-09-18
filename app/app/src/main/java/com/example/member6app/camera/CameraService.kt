package com.example.member6app.camera

import android.content.Context
import android.graphics.ImageFormat
import android.util.Log
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.concurrent.Executors

/**
 * CameraService — Rear camera capture using CameraX ImageAnalysis.
 *
 * Resolution: 640x480 (configurable). Lower resolution reduces processing latency
 * while retaining sufficient feature density for optical flow.
 *
 * Timestamp: ImageProxy.imageInfo.timestamp is boot-clock nanoseconds (same domain
 * as SensorEvent.timestamp). This is as close to hardware capture time as CameraX
 * exposes. There IS still pipeline latency between capture and delivery; this
 * uncertainty is documented and not hidden.
 *
 * Threading: Analysis runs on a dedicated single-thread executor. This ensures
 * vision processing never blocks the 100 Hz IMU thread.
 *
 * Frame dropping: CameraX drops frames automatically when the analyser is busy
 * (STRATEGY_KEEP_ONLY_LATEST). We do not process every frame.
 */
class CameraService(private val context: Context) {

    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val visionPipeline   = VisionPipeline()

    private val _isRunning      = MutableStateFlow(false)
    val isRunning: StateFlow<Boolean> = _isRunning

    private val _diagnostics    = MutableStateFlow(CameraDiagnostics())
    val diagnostics: StateFlow<CameraDiagnostics> = _diagnostics

    private var frameCount      = 0L
    private var startNs         = 0L

    fun start(lifecycleOwner: LifecycleOwner) {
        val providerFuture = ProcessCameraProvider.getInstance(context)
        providerFuture.addListener({
            val provider = providerFuture.get()

            val imageAnalysis = ImageAnalysis.Builder()
                .setTargetResolution(Size(640, 480))
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                .build()

            imageAnalysis.setAnalyzer(analysisExecutor) { imageProxy ->
                processFrame(imageProxy)
            }

            val selector = CameraSelector.DEFAULT_BACK_CAMERA

            try {
                provider.unbindAll()
                provider.bindToLifecycle(lifecycleOwner, selector, imageAnalysis)
                _isRunning.value = true
                startNs = System.nanoTime()
                Log.i(TAG, "Camera started (640x480, rear)")
            } catch (e: Exception) {
                Log.e(TAG, "Camera bind failed: ${e.message}")
                _isRunning.value = false
            }
        }, ContextCompat.getMainExecutor(context))
    }

    fun stop() {
        analysisExecutor.shutdown()
        _isRunning.value = false
        Log.i(TAG, "Camera stopped")
    }

    private fun processFrame(imageProxy: ImageProxy) {
        val captureTs = imageProxy.imageInfo.timestamp / 1_000_000_000.0  // boot-clock seconds
        frameCount++

        // Compute FPS
        val elapsedS = (System.nanoTime() - startNs) / 1e9
        val fps = if (elapsedS > 0) frameCount / elapsedS else 0.0

        try {
            val result = visionPipeline.process(imageProxy, captureTs)
            _diagnostics.value = CameraDiagnostics(
                fps               = fps,
                frameCount        = frameCount,
                visionConfidence  = result.confidence,
                visionStatus      = result.status,
                processingLatencyMs = result.processingMs,
                captureTimestamp  = captureTs
            )
        } catch (e: Exception) {
            Log.e(TAG, "Vision pipeline error: ${e.message}")
        } finally {
            imageProxy.close()
        }
    }

    companion object {
        private const val TAG = "CameraService"
    }
}

data class CameraDiagnostics(
    val fps: Double              = 0.0,
    val frameCount: Long         = 0L,
    val visionConfidence: Double = 0.0,
    val visionStatus: String     = "UNINIT",
    val processingLatencyMs: Long = 0L,
    val captureTimestamp: Double = 0.0
)
