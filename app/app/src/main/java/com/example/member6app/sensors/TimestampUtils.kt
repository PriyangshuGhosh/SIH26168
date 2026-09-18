package com.example.member6app.sensors

/**
 * Timestamp utility — documents the timestamp domains used in this app.
 *
 * ANDROID SENSOR DOMAIN (used by this app):
 *   SensorEvent.timestamp           → CLOCK_BOOTTIME, nanoseconds since boot
 *   Location.elapsedRealtimeNanos   → CLOCK_BOOTTIME, nanoseconds since boot
 *   ImageProxy.imageInfo.timestamp  → CLOCK_BOOTTIME, nanoseconds (CameraX)
 *
 * All three sources use the same clock domain on modern Android (API 26+).
 * Relative synchronization between IMU, GNSS, and camera is therefore
 * possible to within the hardware-software pipeline latency of each sensor.
 *
 * KNOWN SYNCHRONIZATION UNCERTAINTIES:
 *   IMU:    Typically < 1 ms pipeline latency (hardware FIFO delivery)
 *   GNSS:   Typically 100–500 ms between GPS fix and Location callback
 *   Camera: CameraX timestamp = hardware capture time; delivery latency ~5–30 ms
 *
 * WALL-CLOCK TIME IS NOT USED as the primary synchronization source.
 * System.currentTimeMillis() is used only for performance measurement (FPS etc.).
 *
 * NATIVE ENGINE (Member 5 / Member 2):
 *   Receives timestamps in SECONDS from boot-clock.
 *   Conversion: nanoseconds / 1_000_000_000.0
 */
object TimestampUtils {

    /**
     * Convert boot-clock nanoseconds to seconds (for native engine).
     */
    fun nsToSeconds(ns: Long): Double = ns / 1_000_000_000.0

    /**
     * Returns true if the new timestamp represents a regression relative
     * to the last seen timestamp.
     */
    fun isRegression(newTs: Double, lastTs: Double): Boolean =
        lastTs > 0.0 && newTs <= lastTs

    /**
     * Returns true if the new timestamp represents a suspicious gap
     * (more than [maxGapSeconds] elapsed since last event).
     * Default: 1.0 s gap for IMU (would indicate dropout).
     */
    fun isSuspiciousGap(newTs: Double, lastTs: Double, maxGapSeconds: Double = 1.0): Boolean =
        lastTs > 0.0 && (newTs - lastTs) > maxGapSeconds
}
