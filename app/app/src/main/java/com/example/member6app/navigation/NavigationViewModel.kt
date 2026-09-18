package com.example.member6app.navigation

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.member6app.camera.CameraService
import com.example.member6app.camera.VisionAdapter
import com.example.member6app.native.EngineBridge
import com.example.member6app.sensors.GnssService
import com.example.member6app.sensors.ImuService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * NavigationViewModel — coordinates all sensor services, the native engine,
 * and exposes a single [uiState] flow for the UI.
 *
 * Engine polling: ~10 Hz via a coroutine loop. This is the ONLY place that
 * calls idr_get_current_state(). The UI observes [uiState].
 *
 * Sensor threading model:
 *   IMU callbacks → sensor thread → idr_feed_imu (single producer, SPSC OK)
 *   GNSS callbacks → main/location thread → idr_feed_gnss
 *   Vision → analysis executor → VisionAdapter (read-only state update)
 *   State polling → Dispatchers.Default coroutine → UI StateFlow
 *
 * The IMU and state-polling paths never block each other.
 */
class NavigationViewModel(app: Application) : AndroidViewModel(app) {

    val imuService    = ImuService(app)
    val gnssService   = GnssService(app)
    val cameraService = CameraService(app)
    private val visionAdapter = VisionAdapter()

    private val _uiState = MutableStateFlow(NavigationUiState())
    val uiState: StateFlow<NavigationUiState> = _uiState

    private var pollJob: Job? = null

    // ── Engine init ───────────────────────────────────────────────────────────

    /**
     * Initialize the native engine. Call once, after permissions are granted.
     *
     * mapDbPath and onnxModelPath may be "" during parallel development.
     * The engine will run in degraded/stub mode in that case.
     */
    fun initEngine(mapDbPath: String = "", onnxModelPath: String = "") {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val result = EngineBridge.init(mapDbPath, onnxModelPath)
                if (result == 1) {
                    Log.i(TAG, "Native engine initialized OK (map='$mapDbPath', model='$onnxModelPath')")
                    _uiState.value = _uiState.value.copy(
                        engineInitialized = true,
                        mode = NavigationMode.NO_FIX,
                        mapStatus = if (mapDbPath.isEmpty()) "NO_MAP_PATH" else "LOADING"
                    )
                    startPolling()
                } else {
                    val err = EngineBridge.getLastError()
                    Log.e(TAG, "Native engine FAILED: $err")
                    _uiState.value = _uiState.value.copy(
                        engineInitialized = false,
                        mode = NavigationMode.ENGINE_FAILED,
                        engineError = err.ifEmpty { "idr_engine_init returned 0" }
                    )
                }
            } catch (e: UnsatisfiedLinkError) {
                val msg = "libidr_engine.so not found or wrong ABI: ${e.message}"
                Log.e(TAG, msg)
                _uiState.value = _uiState.value.copy(
                    engineInitialized = false,
                    mode = NavigationMode.ENGINE_FAILED,
                    engineError = msg
                )
            }
        }
    }

    // ── Sensors ───────────────────────────────────────────────────────────────

    fun startSensors() {
        imuService.start()
        gnssService.start()
        Log.i(TAG, "Sensors started")
    }

    fun stopSensors() {
        imuService.stop()
        gnssService.stop()
        Log.i(TAG, "Sensors stopped")
    }

    // ── GNSS outage simulation ────────────────────────────────────────────────

    fun simulateGnssOutage(active: Boolean) {
        gnssService.gnssOutageSimulated = active
        // UI mode update happens in polling loop by reading is_dead_reckoning
        // We also set the GNSS_OUTAGE_SIM mode immediately for feedback
        if (active) {
            _uiState.value = _uiState.value.copy(mode = NavigationMode.GNSS_OUTAGE_SIM)
        }
        // On deactivation, mode will revert to GNSS_AIDED or DEAD_RECKONING
        // based on the next idr_get_current_state() result (~10 Hz)
        Log.i(TAG, "GNSS outage simulation: $active")
    }

    val isGnssOutageSimulated get() = gnssService.gnssOutageSimulated

    // ── Navigation reset ─────────────────────────────────────────────────────

    fun resetNavigation(mapDbPath: String = com.example.member6app.MainActivity.MAP_DB_PATH, onnxModelPath: String = com.example.member6app.MainActivity.ONNX_MODEL_PATH) {
        Log.i(TAG, "Resetting navigation engine")
        viewModelScope.launch(Dispatchers.IO) {
            pollJob?.cancel()
            EngineBridge.shutdown()
            delay(100)
            initEngine(mapDbPath, onnxModelPath)
        }
    }

    // ── State polling ~10 Hz ──────────────────────────────────────────────────

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch(Dispatchers.Default) {
            while (isActive) {
                try {
                    val nav = EngineBridge.getCurrentState()

                    // Determine mode from native flag and simulation state
                    val mode = when {
                        gnssService.gnssOutageSimulated -> NavigationMode.GNSS_OUTAGE_SIM
                        nav.isDeadReckoning != 0        -> NavigationMode.DEAD_RECKONING
                        nav.lat == 0.0 && nav.lon == 0.0 -> NavigationMode.NO_FIX
                        else                             -> NavigationMode.GNSS_AIDED
                    }

                    val gnssInfo = gnssService.gnssStatus.value
                    val camDiag  = cameraService.diagnostics.value
                    
                    // User Request: Use raw GPS speed when available and not in outage.
                    // Use ML model speed (nav.speedMs) ONLY when GNSS outage is simulated.
                    val rawGps = gnssService.lastLocation.value
                    val gpsSpeedKmh = if (rawGps != null && rawGps.hasSpeed()) rawGps.speed * 3.6 else 0.0
                    
                    val displaySpeedKmh = if (!gnssService.gnssOutageSimulated && gnssInfo.available) {
                        gpsSpeedKmh
                    } else {
                        nav.speedMs * 3.6
                    }

                    _uiState.value = _uiState.value.copy(
                        mode             = mode,
                        latitude         = nav.lat,
                        longitude        = nav.lon,
                        speedKmh         = displaySpeedKmh,
                        headingDeg       = nav.headingDeg,
                        confidence       = nav.confidence,
                        gnssAvailable    = gnssInfo.available,
                        gnssSatellites   = gnssInfo.satellites,
                        gnssAccuracy     = gnssInfo.accuracy,
                        visionConfidence = camDiag.visionConfidence,
                        visionStatus     = camDiag.visionStatus,
                        imuHz            = imuService.measuredHz.value,
                        cameraFps        = camDiag.fps
                    )
                } catch (e: Exception) {
                    Log.e(TAG, "State poll error: ${e.message}")
                }
                delay(100)  // 10 Hz
            }
        }
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    override fun onCleared() {
        super.onCleared()
        pollJob?.cancel()
        imuService.stop()
        gnssService.stop()
        cameraService.stop()
        try {
            EngineBridge.shutdown()
            Log.i(TAG, "Native engine shut down cleanly")
        } catch (e: Exception) {
            Log.w(TAG, "Engine shutdown error: ${e.message}")
        }
    }

    companion object {
        private const val TAG = "NavigationViewModel"
    }
}
