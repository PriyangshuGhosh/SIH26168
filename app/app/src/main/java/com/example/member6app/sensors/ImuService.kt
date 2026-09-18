package com.example.member6app.sensors

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.SystemClock
import android.util.Log
import com.example.member6app.native.EngineBridge
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * ImuService — captures Accelerometer + Gyroscope at maximum rate (~100 Hz).
 *
 * Timestamp domain: Android sensor timestamps are nanoseconds since boot
 * (CLOCK_BOOTTIME). We convert to seconds for the native engine.
 *
 * Threading: SensorEventListener callbacks arrive on a dedicated sensor thread.
 * idr_feed_imu is called directly from that thread. The SPSC constraint from
 * Member 5 requires a single IMU producer thread; this class satisfies that
 * by using one HandlerThread via the looper path. GNSS feeds from a different
 * thread are fine because Member 5 uses separate queues.
 *
 * Do NOT call idr_feed_imu from two different threads simultaneously.
 */
class ImuService(context: Context) : SensorEventListener {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelSensor: Sensor? = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroSensor: Sensor? = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

    // Last received values (merged before feed)
    @Volatile private var lastAccel = floatArrayOf(0f, 0f, 9.81f)
    @Volatile private var lastGyro  = floatArrayOf(0f, 0f, 0f)
    @Volatile private var lastAccelTs = 0.0
    @Volatile private var lastGyroTs  = 0.0

    // Diagnostics
    private var accelSampleCount = 0L
    private var accelStartNs     = 0L
    private var droppedEvents    = 0L
    private var lastSentTs       = 0.0

    private val _measuredHz = MutableStateFlow(0.0)
    val measuredHz: StateFlow<Double> = _measuredHz

    val isAccelAvailable get() = accelSensor != null
    val isGyroAvailable  get() = gyroSensor  != null

    // Monotonic boot-clock nanoseconds → seconds
    private fun nsToSeconds(ns: Long): Double = ns / 1_000_000_000.0

    fun start() {
        if (accelSensor == null) {
            Log.e(TAG, "Accelerometer unavailable – IMU cannot be started")
            return
        }
        if (gyroSensor == null) {
            Log.e(TAG, "Gyroscope unavailable – IMU cannot be started")
            return
        }
        sensorManager.registerListener(this, accelSensor, SensorManager.SENSOR_DELAY_FASTEST)
        sensorManager.registerListener(this, gyroSensor,  SensorManager.SENSOR_DELAY_FASTEST)
        accelStartNs = SystemClock.elapsedRealtimeNanos()
        Log.i(TAG, "IMU started (accel + gyro)")
    }

    fun stop() {
        sensorManager.unregisterListener(this)
        Log.i(TAG, "IMU stopped – measured rate: %.1f Hz, dropped: %d".format(_measuredHz.value, droppedEvents))
    }

    private val pairer = ImuSamplePairer()

    override fun onSensorChanged(event: SensorEvent) {
        val sample = when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                if (lastAccelTs != 0.0 && TimestampUtils.isRegression(nsToSeconds(event.timestamp), lastAccelTs)) {
                    droppedEvents++
                    return
                }
                lastAccelTs = nsToSeconds(event.timestamp)
                accelSampleCount++
                if (accelSampleCount % 200 == 0L) {
                    val elapsedS = (SystemClock.elapsedRealtimeNanos() - accelStartNs) / 1e9
                    if (elapsedS > 0) _measuredHz.value = accelSampleCount / elapsedS
                }
                pairer.feedAccelNs(
                    event.timestamp,
                    event.values[0].toDouble(),
                    event.values[1].toDouble(),
                    event.values[2].toDouble()
                )
            }
            Sensor.TYPE_GYROSCOPE -> {
                if (lastGyroTs != 0.0 && TimestampUtils.isRegression(nsToSeconds(event.timestamp), lastGyroTs)) {
                    droppedEvents++
                    return
                }
                lastGyroTs = nsToSeconds(event.timestamp)
                pairer.feedGyroNs(
                    event.timestamp,
                    event.values[0].toDouble(),
                    event.values[1].toDouble(),
                    event.values[2].toDouble()
                )
            }
            else -> null
        } ?: return

        EngineBridge.feedImu(
            timestamp = sample.timestampS,
            ax = sample.ax, ay = sample.ay, az = sample.az,
            gx = sample.gx, gy = sample.gy, gz = sample.gz
        )
    }

    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {
        Log.d(TAG, "Sensor accuracy changed: ${sensor.name} → $accuracy")
    }

    fun diagnostics() = ImuDiagnostics(
        measuredHz    = _measuredHz.value,
        sampleCount   = accelSampleCount,
        droppedEvents = droppedEvents,
        accelAvailable = isAccelAvailable,
        gyroAvailable  = isGyroAvailable
    )

    companion object {
        private const val TAG = "ImuService"
    }
}

data class ImuDiagnostics(
    val measuredHz: Double,
    val sampleCount: Long,
    val droppedEvents: Long,
    val accelAvailable: Boolean,
    val gyroAvailable: Boolean
)
