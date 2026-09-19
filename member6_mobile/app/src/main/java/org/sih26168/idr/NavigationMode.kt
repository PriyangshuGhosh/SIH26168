package org.sih26168.idr

enum class NavigationMode {
    INITIALIZING,
    WAITING_FOR_GNSS,
    GNSS_AIDED,
    DEAD_RECKONING,
    SIMULATED_OUTAGE,
    MAP_UNAVAILABLE,
    ENGINE_ERROR,
    REPLAY,
    EXPERIMENT
}

fun NavigationMode.label(): String = when (this) {
    NavigationMode.INITIALIZING -> "INITIALIZING"
    NavigationMode.WAITING_FOR_GNSS -> "WAITING FOR GNSS"
    NavigationMode.GNSS_AIDED -> "GNSS-AIDED"
    NavigationMode.DEAD_RECKONING -> "DEAD RECKONING"
    NavigationMode.SIMULATED_OUTAGE -> "SIMULATED GNSS OUTAGE"
    NavigationMode.MAP_UNAVAILABLE -> "MAP DATA NOT AVAILABLE"
    NavigationMode.ENGINE_ERROR -> "ENGINE ERROR"
    NavigationMode.REPLAY -> "REPLAY"
    NavigationMode.EXPERIMENT -> "EXPERIMENT"
}

object NavModeResolver {
    fun resolve(
        engineError: String?,
        initialized: Boolean,
        replay: Boolean,
        experiment: Boolean,
        simulateOutage: Boolean,
        hasRawGps: Boolean,
        snapshot: NavSnapshot?,
        mapUnavailable: Boolean
    ): NavigationMode {
        if (!engineError.isNullOrBlank()) return NavigationMode.ENGINE_ERROR
        if (!initialized) return NavigationMode.INITIALIZING
        if (experiment) return NavigationMode.EXPERIMENT
        if (replay) return NavigationMode.REPLAY
        if (mapUnavailable) return NavigationMode.MAP_UNAVAILABLE
        if (simulateOutage) return NavigationMode.SIMULATED_OUTAGE
        if (snapshot?.isDeadReckoning == true) return NavigationMode.DEAD_RECKONING
        if (!hasRawGps) return NavigationMode.WAITING_FOR_GNSS
        return NavigationMode.GNSS_AIDED
    }
}
