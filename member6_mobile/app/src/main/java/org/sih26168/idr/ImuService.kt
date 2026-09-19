package org.sih26168.idr

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager

/**
 * 100 Hz-class IMU ingest. Callbacks stay cheap: pair by timestamp, then one JNI feed.
 * Map loading is never done here.
 */
class ImuService(
    private val sensorManager: SensorManager,
    private val onSample: (ImuSamplePairer.Sample) -> Unit
) : SensorEventListener {
    private val pairer = ImuSamplePairer()
    private val accel = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyro = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

    fun start() {
        pairer.reset()
        accel?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_FASTEST) }
        gyro?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_FASTEST) }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    override fun onSensorChanged(event: SensorEvent) {
        val v = event.values
        if (v.size < 3) return
        val sample = when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> pairer.feedAccelNs(event.timestamp, v[0].toDouble(), v[1].toDouble(), v[2].toDouble())
            Sensor.TYPE_GYROSCOPE -> pairer.feedGyroNs(event.timestamp, v[0].toDouble(), v[1].toDouble(), v[2].toDouble())
            else -> null
        }
        if (sample != null) {
            onSample(sample)
        }
    }
}
