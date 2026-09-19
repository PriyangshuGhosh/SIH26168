package org.sih26168.idr

import android.Manifest
import android.content.pm.PackageManager
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.sih26168.idr.ui.IdrTheme
import org.sih26168.idr.ui.NavigationScreen
import java.io.File

class MainActivity : ComponentActivity(), LocationListener {
    private val vm = NavigationViewModel(EngineBridge)
    private var imu: ImuService? = null
    private var locationManager: LocationManager? = null
    private var pollJob: Job? = null
    private var roadsLoaded = false
    private lateinit var mapsDir: File
    private lateinit var roadMgr: LocalRoadDataManager
    private var sessionLog: SessionLogger? = null
    private var v2vStarted = false

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted[Manifest.permission.ACCESS_FINE_LOCATION] == true) startGnss()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        mapsDir = File(filesDir, "maps")
        AssetProvisioner.copyAssetTree(this, "maps", mapsDir)
        roadMgr = LocalRoadDataManager(mapsDir)
        val manifest = File(mapsDir, "manifest.json")
        val onnxAsset = File(filesDir, "speed_estimator.onnx")
        val onnxPath = if (onnxAsset.exists() && onnxAsset.length() > 16 && !onnxAsset.readText().trim().startsWith("mock")) {
            onnxAsset.absolutePath
        } else {
            "mock"
        }
        val ok = EngineBridge.init(manifest.absolutePath, onnxPath)
        vm.markEngine(ok, if (ok) null else EngineBridge.lastError().ifBlank { "init failed" })
        vm.setStorage(roadMgr.storageInfo())
        sessionLog = SessionLogger(File(filesDir, "logs/session.jsonl"))

        setContent {
            val ui by vm.state.collectAsStateWithLifecycle()
            IdrTheme {
                NavigationScreen(
                    state = ui,
                    onToggleOutage = {
                        vm.toggleOutage()
                        val now = System.nanoTime() * 1e-9
                        sessionLog?.outage(now, vm.state.value.simulateOutage)
                    }
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        val sm = getSystemService(SENSOR_SERVICE) as SensorManager
        imu = ImuService(sm) { sample ->
            EngineBridge.feedImu(sample.timestampS, sample.ax, sample.ay, sample.az, sample.gx, sample.gy, sample.gz)
            sessionLog?.imu(sample.timestampS, sample.ax, sample.ay, sample.az, sample.gx, sample.gy, sample.gz)
        }
        imu?.start()
        locationManager = getSystemService(LOCATION_SERVICE) as LocationManager
        requestPerms()
        pollJob = lifecycleScope.launch(Dispatchers.Default) {
            while (isActive) {
                val snap = EngineBridge.poll()
                val diag = EngineBridge.diagnostics()
                if (snap != null && !roadsLoaded) {
                    val pack = File(mapsDir, "synthetic_grid.roadpack")
                    val osm = File(mapsDir, "regions").listFiles()?.firstOrNull()
                    val chosen = when {
                        snap.regionId.contains("synthetic") && pack.isFile -> pack
                        osm != null -> osm
                        pack.isFile -> pack
                        else -> null
                    }
                    chosen?.readText()?.let { RoadpackParser.parse(it)?.let { g -> vm.setRoads(g) } }
                    roadsLoaded = true
                    if (!v2vStarted && EngineBridge.nativeAvailable) {
                        runCatching { V2vBridge.nativeStartSimulated(snap.lat, snap.lon) }
                        v2vStarted = true
                    }
                }
                val v2v = if (v2vStarted && snap != null) {
                    runCatching {
                        V2vBridge.snapshot(snap.timestamp, snap, !vm.state.value.simulateOutage && snap.isDeadReckoning.not())
                    }.getOrNull()
                } else null
                val approaching = vm.state.value.rawGps?.let {
                    roadMgr.selectForLocation(it.lat, it.lon)
                    roadMgr.approachingBoundary(it.lat, it.lon, 80.0)
                } ?: false
                vm.onPoll(snap, diag, v2v, approaching)
                delay(100)
            }
        }
    }

    override fun onStop() {
        pollJob?.cancel()
        imu?.stop()
        locationManager?.removeUpdates(this)
        super.onStop()
    }

    override fun onDestroy() {
        runCatching { V2vBridge.nativeStop() }
        EngineBridge.shutdown()
        super.onDestroy()
    }

    private fun requestPerms() {
        val need = arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        if (need.any { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }) {
            permissionLauncher.launch(need)
        } else {
            startGnss()
        }
    }

    private fun startGnss() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            return
        }
        locationManager?.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, this)
    }

    override fun onLocationChanged(location: Location) {
        val t = location.elapsedRealtimeNanos * 1.0e-9
        val speed = if (location.hasSpeed()) location.speed.toDouble() else Double.NaN
        val feed = !vm.state.value.simulateOutage && !vm.state.value.replayActive
        val hdop = if (location.hasAccuracy()) (location.accuracy / 5.0).toDouble() else 1.0
        // Sample the engine estimate BEFORE the fix is fed: feeding snaps the output to GNSS.
        val preFeedEstimate = if (feed) {
            EngineBridge.poll()?.let { GeoPoint(it.timestamp, it.lat, it.lon) }
        } else null
        if (feed) {
            EngineBridge.selectMap(location.latitude, location.longitude)
            EngineBridge.feedGnss(
                t, location.latitude, location.longitude, location.altitude,
                speed, hdop, 8 // speed is NaN when !hasSpeed(): unknown, never 0.0
            )
            sessionLog?.gnss(t, location.latitude, location.longitude, location.altitude, speed, hdop, 8)
        }
        vm.onRawGps(t, location.latitude, location.longitude, speed, location.hasSpeed(),
            if (location.hasAccuracy()) location.accuracy.toDouble() else Double.NaN, feed, preFeedEstimate)
        roadMgr.selectForLocation(location.latitude, location.longitude)
        vm.setStorage(roadMgr.storageInfo())
        if (!roadsLoaded) {
            val cover = roadMgr.findCovering(location.latitude, location.longitude)
            cover?.let { File(it.roadpackPath).takeIf { f -> f.isFile }?.readText() }
                ?.let { RoadpackParser.parse(it) }
                ?.let { vm.setRoads(it); roadsLoaded = true }
        }
    }
}
