package com.example.member6app.native

object EngineBridge {
    init {
        System.loadLibrary("member6_jni")
    }

    external fun init(mapPath: String, modelPath: String): Int
    external fun shutdown()
    external fun feedImu(timestamp: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double)
    external fun feedGnss(timestamp: Double, lat: Double, lon: Double, alt: Double, speed: Double, hdop: Double, numSats: Int)
    external fun getCurrentState(): IDRNavigationOutput
    external fun getLastError(): String
}
