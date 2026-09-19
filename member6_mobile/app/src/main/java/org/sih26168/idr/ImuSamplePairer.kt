package org.sih26168.idr

/**
 * Pairs independent accelerometer and gyroscope SensorEvents by timestamp.
 * Timestamps are SensorEvent.timestamp nanoseconds; output is seconds for idr_feed_imu.
 */
class ImuSamplePairer(private val maxSkewSeconds: Double = 0.008) {
    private var haveAccel = false
    private var haveGyro = false
    private var accelT = 0.0
    private var gyroT = 0.0
    private var ax = 0.0
    private var ay = 0.0
    private var az = 0.0
    private var gx = 0.0
    private var gy = 0.0
    private var gz = 0.0
    private var lastOut = 0.0
    private var haveOut = false

    data class Sample(
        val timestampS: Double,
        val ax: Double,
        val ay: Double,
        val az: Double,
        val gx: Double,
        val gy: Double,
        val gz: Double
    )

    fun reset() {
        haveAccel = false
        haveGyro = false
        haveOut = false
    }

    fun feedAccelNs(timestampNs: Long, ax: Double, ay: Double, az: Double): Sample? {
        if (!timestampNs.toDouble().isFinite()) return null
        accelT = timestampNs * 1.0e-9
        this.ax = ax
        this.ay = ay
        this.az = az
        haveAccel = true
        return maybeEmit()
    }

    fun feedGyroNs(timestampNs: Long, gx: Double, gy: Double, gz: Double): Sample? {
        gyroT = timestampNs * 1.0e-9
        this.gx = gx
        this.gy = gy
        this.gz = gz
        haveGyro = true
        return maybeEmit()
    }

    private fun maybeEmit(): Sample? {
        if (!haveAccel || !haveGyro) return null
        if (kotlin.math.abs(accelT - gyroT) > maxSkewSeconds) return null
        val t = 0.5 * (accelT + gyroT)
        if (haveOut && t <= lastOut) return null
        haveOut = true
        lastOut = t
        return Sample(t, ax, ay, az, gx, gy, gz)
    }
}
