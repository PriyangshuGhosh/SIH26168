package com.vizag.nav

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.vizag.nav.ui.MapScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {

    companion object {
        private const val TAG = "MainActivity"
        private const val POLL_MS = 100L   // 10 Hz update cycle
    }

    private lateinit var gnssManager: GnssManager
    private lateinit var imuManager:  ImuManager
    private lateinit var onnx:        OnnxInference
    private val dr = DeadReckoningEngine()

    private var navState    by mutableStateOf(NavState())
    private var simOutage   by mutableStateOf(false)

    private val timeFormat = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)

    private fun addLog(msg: String) {
        val timestamp = timeFormat.format(Date())
        val logEntry = "[${timestamp}] ${msg}"
        navState = navState.copy(
            dashboardLogs = listOf(logEntry) + navState.dashboardLogs.take(49)
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        gnssManager = GnssManager(this)
        imuManager  = ImuManager(this)
        onnx        = OnnxInference(this)

        setContent {
            val view = androidx.compose.ui.platform.LocalView.current
            if (!view.isInEditMode) {
                androidx.compose.runtime.SideEffect {
                    val window = (view.context as android.app.Activity).window
                    window.statusBarColor = android.graphics.Color.TRANSPARENT
                }
            }

            MaterialTheme {
                val context = LocalContext.current
                if (navState.mode == NavMode.INITIALIZING) {
                    WaitingScreen()
                } else {
                    MapScreen(
                        state = navState.copy(
                            isImuActive = imuManager.isActive,
                            isOnnxReady = onnx.isReady,
                            isGnssActive = !navState.isGpsStale
                        ),
                        simulateOutage = simOutage,
                        onToggleOutage = { simOutage = !simOutage },
                        onUpdateState = { navState = it },
                        context = context
                    )
                }
            }
        }

        requestPermissionsAndStart()
    }

    private fun requestPermissionsAndStart() {
        val perms = arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        val allGranted = perms.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
        if (allGranted) {
            startServices()
        } else {
            registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
                if (results.values.any { it }) startServices()
                else {
                    navState = navState.copy(mode = NavMode.DEAD_RECKONING)
                    startDrLoop()
                }
            }.launch(perms)
        }
    }

    private fun startServices() {
        imuManager.start()
        gnssManager.start()


        lifecycleScope.launch {
            gnssManager.data.collect { fix ->
                if (fix == null || simOutage) return@collect
                
                // IGNORE noisy indoor GPS fixes that cause "hovering"
                if (fix.accuracyM > 20f) return@collect

                // Only update GPS position if it has moved significantly (prevents micro-hovering)
                val results = FloatArray(1)
                android.location.Location.distanceBetween(navState.lat, navState.lon, fix.lat, fix.lon, results)
                val distFromLast = results[0]
                
                if (navState.mode == NavMode.GPS && distFromLast < 3.0f) {
                    // Ignored micro-jump (hovering)
                    return@collect
                }

                // Compare drift if returning from DR
                if (navState.mode == NavMode.DEAD_RECKONING) {

                    val results = FloatArray(1)
                    android.location.Location.distanceBetween(navState.lat, navState.lon, fix.lat, fix.lon, results)
                    val drift = results[0]
                    addLog("Member 2 (GPS): Signal restored. Drift error vs ML: m")
                }

                dr.seedFromGps(fix.lat, fix.lon, if (fix.hasBearing) fix.bearingDeg else navState.headingDeg)

                navState = navState.copy(
                    mode       = NavMode.GPS,
                    lat        = fix.lat,
                    lon        = fix.lon,

                    speedMps   = if (fix.speedMps < 1.5f) 0f else fix.speedMps,

                    headingDeg = if (fix.hasBearing) fix.bearingDeg else navState.headingDeg,
                    accuracyM  = fix.accuracyM,
                    lastGpsFix = fix.fixTimeMs
                )
            }
        }

        startDrLoop()
    }

    private fun startDrLoop() {
        lifecycleScope.launch(Dispatchers.Default) {
            while (true) {
                delay(POLL_MS)
                val gpsActive = !simOutage && !navState.isGpsStale
                if (gpsActive) {
                    if (navState.mode != NavMode.GPS && navState.mode != NavMode.INITIALIZING) {
                        withContext(Dispatchers.Main) { navState = navState.copy(mode = NavMode.GPS) }
                    }
                    continue
                }

                // GPS lost — explicitly switch to DEAD_RECKONING so isDrMode = true
                // and the ONNX ML model is actually invoked on the next check below.
                if (navState.mode != NavMode.DEAD_RECKONING) {
                    // Reset the IMU buffer: discard any stale pre-outage samples so the
                    // ML model starts fresh with post-outage data only (matches
                    // ProductionWindowBuffer reset on non-FULLY_ALIGNED status).
                    imuManager.resetBuffer()
                    withContext(Dispatchers.Main) {
                        navState = navState.copy(mode = NavMode.DEAD_RECKONING)
                    }
                }

                val isDrMode = navState.mode == NavMode.DEAD_RECKONING
                val window = imuManager.getWindow()
                
                // ONLY run ML model when GPS is lost (Dead Reckoning mode)
                val result = if (window != null && isDrMode) {
                    val p = withContext(Dispatchers.IO) { onnx.predict(window) }
                    withContext(Dispatchers.Main) { 
                        addLog("Member 1 (ML): Analyzing IMU data (200 points)")
                        addLog("Member 1 (ML): Output speed ${String.format("%.2f", (p?.velocityMps ?: 0f) * 3.6f)} km/h")
                    }
                    p
                } else null



                val deltaYaw = imuManager.getAndResetYawDeltaRad()
                val (drLat, drLon) = dr.step(result, deltaYaw, navState.travelMode)

                withContext(Dispatchers.Main) {
                    if (navState.mode == NavMode.DEAD_RECKONING) {
                        navState = navState.copy(
                            lat             = drLat,
                            lon             = drLon,
                            speedMps        = dr.currentSpeedMps(),
                            headingDeg      = dr.currentHeading(),
                            speedConfidence = result?.confidence ?: 0f
                        )
                    } else if (navState.mode == NavMode.GPS) {
                        dr.seedFromGps(navState.lat, navState.lon, navState.headingDeg)
                    }
                }
            }
        }
    }

}

@Composable
fun WaitingScreen() {
    Box(Modifier.fillMaxSize().background(Color.White), contentAlignment = Alignment.Center) {
        Text("Waiting for GPS...", fontSize = 18.sp, fontWeight = FontWeight.Medium)
    }
}
