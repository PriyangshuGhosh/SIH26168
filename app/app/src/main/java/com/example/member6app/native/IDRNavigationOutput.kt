package com.example.member6app.native

data class IDRNavigationOutput(
    val timestamp: Double,
    val lat: Double,
    val lon: Double,
    val headingDeg: Double,
    val speedMs: Double,
    val confidence: Double,
    val isDeadReckoning: Int
)
