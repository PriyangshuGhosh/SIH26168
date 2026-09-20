package com.vizag.nav

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager

/**
 * Acquires accelerometer + gyroscope at ~100 Hz and maintains a ring buffer
 * of the last 200 paired samples — exactly what the ONNX model expects.
 *
 * Channel order: [ax, ay, az, gx, gy, gz] (SI units: m/s², rad/s)
 *
 * IMPORTANT: A sample is only pushed to the ring buffer once BOTH accel AND
 * gyro have delivered a fresh reading for the same time slot. This matches the
 * ProductionWindowBuffer FULLY_ALIGNED gating in member1-ml's
 * member2_interface.py and prevents the systematic gyro-lag that occurred
 * when pushSample() was called only on accelerometer events.
 */
class ImuManager(context: Context) {

    companion object {
        const val WINDOW_SIZE = 200         // 2 seconds @ 100 Hz
        const val CHANNELS = 6
        const val SENSOR_DELAY_US = 10_000  // ~100 Hz
    }

    private val sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelSensor = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroSensor  = sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

    // Latest raw accel / gyro values
    @Volatile private var ax = 0f; @Volatile private var ay = 0f; @Volatile private var az = 0f
    @Volatile private var gx = 0f; @Volatile private var gy = 0f; @Volatile private var gz = 0f

    // "Fresh" flags: both must be true before we push a paired sample
    @Volatile private var accelFresh = false
    @Volatile private var gyroFresh  = false

    /** Latest gz value in rad/s — used for heading integration. */
    @Volatile var latestGz: Float = 0f
        private set

    val isActive: Boolean get() = synchronized(lock) { count > 0 }

    // Ring buffer: flat FloatArray of [WINDOW_SIZE * CHANNELS]
    private val ring = FloatArray(WINDOW_SIZE * CHANNELS)
    private var head  = 0
    private var count = 0
    private val lock  = Any()

    // Continuous heading integration
    private var lastGyroTimeUs = 0L
    @Volatile private var accumulatedYawRad: Float = 0f

    /** Returns the integrated yaw delta (radians) since the last call, and resets it. */
    fun getAndResetYawDeltaRad(): Float {
        synchronized(lock) {
            val y = accumulatedYawRad
            accumulatedYawRad = 0f
            return y
        }
    }

    /**
     * Reset the ring buffer — call when the sensor pipeline restarts (e.g. GPS
     * just lost, switching to DR mode) so stale pre-outage data does not corrupt
     * the first ML inference after GPS loss.
     */
    fun resetBuffer() {
        synchronized(lock) {
            head  = 0
            count = 0
            accelFresh = false
            gyroFresh  = false
        }
    }

    private val accelListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            ax = e.values[0]; ay = e.values[1]; az = e.values[2]
            synchronized(lock) {
                accelFresh = true
                if (gyroFresh) {           // push only when gyro is also fresh
                    pushSampleLocked()
                    accelFresh = false
                    gyroFresh  = false
                }
            }
        }
        override fun onAccuracyChanged(s: Sensor?, a: Int) = Unit
    }

    private val gyroListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            gx = e.values[0]; gy = e.values[1]; gz = e.values[2]; latestGz = gz

            // Continuous yaw integration (independent of paired-push logic)
            val currentUs = e.timestamp / 1000L
            val dtS = if (lastGyroTimeUs > 0) (currentUs - lastGyroTimeUs) / 1_000_000f else 0.01f
            lastGyroTimeUs = currentUs
            val clampedDt = if (dtS > 0.1f) 0.01f else dtS
            synchronized(lock) {
                accumulatedYawRad += gz * clampedDt
                gyroFresh = true
                if (accelFresh) {          // push only when accel is also fresh
                    pushSampleLocked()
                    accelFresh = false
                    gyroFresh  = false
                }
            }
        }
        override fun onAccuracyChanged(s: Sensor?, a: Int) = Unit
    }

    /** Must be called with `lock` held. */
    private fun pushSampleLocked() {
        val base = head * CHANNELS
        ring[base + 0] = ax; ring[base + 1] = ay; ring[base + 2] = az
        ring[base + 3] = gx; ring[base + 4] = gy; ring[base + 5] = gz
        head = (head + 1) % WINDOW_SIZE
        if (count < WINDOW_SIZE) count++
    }

    /**
     * Returns a [WINDOW_SIZE × CHANNELS] FloatArray in chronological order
     * (oldest first), or null if the buffer is not yet full.
     *
     * The production ONNX graph internally decimates this 200-sample/100 Hz
     * window to 20 samples/10 Hz via raw[9::10] before running its conv blocks.
     * No decimation needed here — pass the raw 200-sample window as-is.
     */
    fun getWindow(): FloatArray? {
        synchronized(lock) {
            if (count < WINDOW_SIZE) return null
            val out = FloatArray(WINDOW_SIZE * CHANNELS)
            for (i in 0 until WINDOW_SIZE) {
                val src = ((head + i) % WINDOW_SIZE) * CHANNELS
                val dst = i * CHANNELS
                System.arraycopy(ring, src, out, dst, CHANNELS)
            }
            return out
        }
    }

    fun start() {
        accelSensor?.let { sm.registerListener(accelListener, it, SENSOR_DELAY_US) }
        gyroSensor?.let  { sm.registerListener(gyroListener,  it, SENSOR_DELAY_US) }
    }

    fun stop() {
        sm.unregisterListener(accelListener)
        sm.unregisterListener(gyroListener)
    }
}

