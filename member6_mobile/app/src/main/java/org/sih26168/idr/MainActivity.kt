package org.sih26168.idr

import android.Manifest
import android.content.pm.PackageManager
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import java.io.File

class MainActivity : AppCompatActivity(), LocationListener {
    private val vm = NavigationViewModel()
    private val handler = Handler(Looper.getMainLooper())
    private var imu: ImuService? = null
    private var locationManager: LocationManager? = null
    private var mapSelected = false
    private val poll = object : Runnable {
        override fun run() {
            EngineBridge.pollSnapshot()?.let { vm.applySnapshot(it) }
            render()
            handler.postDelayed(this, 100)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val mapsDir = File(filesDir, "maps")
        AssetProvisioner.copyAssetTree(this, "maps", mapsDir)
        val manifest = File(mapsDir, "manifest.json")
        val onnx = File(filesDir, "speed_estimator.onnx")
        if (!onnx.exists()) {
            onnx.writeText("mock")
        }
        val mapArg = if (manifest.exists()) manifest.absolutePath else File(mapsDir, "synthetic_grid.roadpack").absolutePath
        EngineBridge.nativeInit(mapArg, "mock")

        findViewById<Button>(R.id.btnOutage).setOnClickListener {
            vm.simulateGnssOutage = !vm.simulateGnssOutage
        }

        val sm = getSystemService(SENSOR_SERVICE) as SensorManager
        imu = ImuService(sm) { sample ->
            EngineBridge.nativeFeedImu(sample.timestampS, sample.ax, sample.ay, sample.az, sample.gx, sample.gy, sample.gz)
        }
        locationManager = getSystemService(LOCATION_SERVICE) as LocationManager
        requestLocation()
        imu?.start()
        handler.post(poll)
    }

    private fun requestLocation() {
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.ACCESS_FINE_LOCATION), 1)
            return
        }
        locationManager?.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, this)
    }

    override fun onLocationChanged(location: Location) {
        if (!mapSelected) {
            mapSelected = EngineBridge.nativeSelectMap(location.latitude, location.longitude)
        }
        if (vm.simulateGnssOutage) return
        val speed = if (location.hasSpeed()) location.speed.toDouble() else 0.0
        val t = location.elapsedRealtimeNanos * 1.0e-9
        val hdop = if (location.hasAccuracy()) (location.accuracy / 5.0).toDouble() else 1.0
        EngineBridge.nativeFeedGnss(t, location.latitude, location.longitude, location.altitude, speed, hdop, 8)
    }

    private fun render() {
        val s = vm.lastSnapshot
        findViewById<TextView>(R.id.txtSpeed).text = vm.speedLabel()
        findViewById<TextView>(R.id.txtMode).text =
            if (s?.isDeadReckoning == true) "DEAD RECKONING" else "GNSS-AIDED"
        findViewById<TextView>(R.id.txtMap).text =
            if (s?.mapStatus?.contains("NOT AVAILABLE") == true) {
                "MAP DATA NOT AVAILABLE"
            } else vm.mapMessage
        findViewById<TextView>(R.id.txtPos).text =
            if (s == null) "—" else String.format("%.6f, %.6f  hdg %.0f°", s.lat, s.lon, s.headingDeg)
        val diag = findViewById<TextView>(R.id.txtDiag)
        if (BuildConfig.DEBUG) {
            diag.visibility = android.view.View.VISIBLE
            val d = DoubleArray(12)
            EngineBridge.nativeDiagnostics(d)
            diag.text = buildString {
                append("diag GNSS ").append("%.2f".format(d[0])).append(" m/s\n")
                append("AI ").append("%.2f".format(d[1])).append("  EKF ").append("%.2f".format(d[2])).append("\n")
                append("display ").append("%.2f".format(d[3])).append(" valid=").append(s?.speedValid).append("\n")
                append("reject ").append(s?.speedRejectReason ?: "").append("\n")
                append("map ").append(s?.mapStatus ?: "").append(" region ").append(s?.regionId ?: "").append("\n")
                append("IMU Hz ").append("%.1f".format(d[8]))
            }
        } else {
            diag.visibility = android.view.View.GONE
        }
    }

    override fun onDestroy() {
        handler.removeCallbacks(poll)
        imu?.stop()
        EngineBridge.nativeShutdown()
        super.onDestroy()
    }
}
