package com.vizag.nav

import android.util.Log
import kotlin.math.PI

class DeadReckoningEngine {

    companion object {
        private const val TAG = "DREngine"
        private const val DT_S = 0.1f     // integration step at 10 Hz polling
        private const val RAD_TO_DEG = (180.0 / PI).toFloat()
    }

    private var seedLat = NavState.VIZAG_CENTER_LAT
    private var seedLon = NavState.VIZAG_CENTER_LON
    private var drLat   = seedLat
    private var drLon   = seedLon
    private var headingDeg = 0f
    private var currentSpeed = 0f
    private var consecutiveMovingSteps = 0

    private var posNorthM = 0.0
    private var posEastM  = 0.0

    fun seedFromGps(lat: Double, lon: Double, bearingDeg: Float) {
        seedLat    = lat
        seedLon    = lon
        headingDeg = bearingDeg
        drLat      = lat
        drLon      = lon
        posNorthM  = 0.0
        posEastM   = 0.0
    }




    fun step(
        onnxResult: OnnxInference.Result?, 
        deltaYawRad: Float, 
        mode: TravelMode
    ): Pair<Double, Double> {
        var clampedYaw = deltaYawRad
        if (Math.abs(clampedYaw) < 0.02f) clampedYaw = 0f
        

        // speed STRICTLY from ML model. 100% ignoring accelerometer pedometers/shakes.
        val rawTargetSpeed = onnxResult?.velocityMps ?: 0f
        
        if (rawTargetSpeed > 1.5f) {
            consecutiveMovingSteps++
        } else {
            consecutiveMovingSteps = 0
        }

        // Time-lock: require 1.5 seconds of sustained ML speed to prevent phone-lift spikes
        val speedMps = if (consecutiveMovingSteps > 15) rawTargetSpeed else 0f


        currentSpeed = speedMps

        if (speedMps > 0f) {
            headingDeg -= clampedYaw * RAD_TO_DEG
            headingDeg  = ((headingDeg % 360f) + 360f) % 360f
        }

        val headingRad = headingDeg * PI / 180.0
        val distM      = speedMps * DT_S
        posNorthM += distM * Math.cos(headingRad)
        posEastM  += distM * Math.sin(headingRad)

        val latDeg = seedLat + posNorthM / 111_320.0
        val lonDeg = seedLon + posEastM  / (111_320.0 * Math.cos(Math.toRadians(seedLat)))
        drLat = latDeg
        drLon = lonDeg

        return Pair(drLat, drLon)
    }




    fun currentHeading(): Float = headingDeg
    fun currentSpeedMps(): Float = currentSpeed
    fun currentLat(): Double    = drLat
    fun currentLon(): Double    = drLon
}
