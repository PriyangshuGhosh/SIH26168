package org.sih26168.idr

class NavigationViewModel {
    @Volatile var simulateGnssOutage: Boolean = false
    @Volatile var lastSnapshot: NavSnapshot? = null
    @Volatile var mapMessage: String = ""
    @Volatile var selectedRegion: String = ""

    fun applySnapshot(s: NavSnapshot) {
        lastSnapshot = s
        mapMessage = if (s.mapStatus.contains("NOT AVAILABLE", ignoreCase = true) || !s.onRoad && s.mapStatus != "in_region") {
            if (s.mapStatus.contains("NOT AVAILABLE")) {
                "Offline map unavailable for this area"
            } else s.mapStatus
        } else {
            s.mapStatus
        }
        selectedRegion = s.regionId
    }

    fun speedLabel(): String {
        val s = lastSnapshot ?: return "Speed unavailable"
        return SpeedDisplay.formatKmh(s.speedMps, s.speedValid)
    }
}
