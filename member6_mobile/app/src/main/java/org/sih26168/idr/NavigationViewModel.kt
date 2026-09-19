package org.sih26168.idr

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class RawGpsView(
    val lat: Double,
    val lon: Double,
    val speedMps: Double,
    val hasSpeed: Boolean,
    val accuracyM: Double
)

data class NavUiState(
    val mode: NavigationMode = NavigationMode.INITIALIZING,
    val snapshot: NavSnapshot? = null,
    val diagnostics: EngineDiagnostics = EngineDiagnostics(),
    val speedLabel: String = "Speed unavailable",
    val rawGps: RawGpsView? = null,
    val simulateOutage: Boolean = false,
    val mapUnavailable: Boolean = false,
    val hardwareNote: String = "REAL HARDWARE VALIDATION: NOT VALIDATED",
    val accuracyNote: String = "SIH GNSS-denied accuracy: NOT VALIDATED",
    val engineError: String? = null,
    val initialized: Boolean = false,
    val outageLive: Boolean = false,
    val outageDurationS: Double = 0.0,
    val lastOutage: OutageRecord? = null,
    val outageHistory: List<OutageRecord> = emptyList(),
    val estimateTrail: List<GeoPoint> = emptyList(),
    val gpsTrail: List<GeoPoint> = emptyList(),
    val roads: RoadpackGraph? = null,
    val v2v: V2vSnapshot? = null,
    val replayActive: Boolean = false,
    val experimentActive: Boolean = false,
    val storage: StorageInfo? = null,
    val activeRegionId: String = "",
    val approachingBoundary: Boolean = false
)

class NavigationViewModel(
    private val engine: EnginePort,
    private val outage: OutageTracker = OutageTracker()
) {
    private val _state = MutableStateFlow(NavUiState())
    val state: StateFlow<NavUiState> = _state.asStateFlow()
    private val gpsTrail = ArrayDeque<GeoPoint>()
    private val estTrail = ArrayDeque<GeoPoint>()

    fun setRoads(graph: RoadpackGraph?) { _state.update { it.copy(roads = graph) } }
    fun setStorage(info: StorageInfo?) { _state.update { it.copy(storage = info) } }

    fun toggleOutage() {
        val next = !_state.value.simulateOutage
        _state.update { it.copy(simulateOutage = next) }
    }

    fun setReplay(active: Boolean) { _state.update { it.copy(replayActive = active) } }
    fun setExperiment(active: Boolean) { _state.update { it.copy(experimentActive = active) } }

    fun markEngine(initialized: Boolean, error: String?) {
        _state.update { it.copy(initialized = initialized, engineError = error) }
        refreshMode()
    }

    fun onRawGps(t: Double, lat: Double, lon: Double, speedMps: Double, hasSpeed: Boolean, accuracyM: Double, feed: Boolean,
                 estimateAtRestore: GeoPoint? = null) {
        val rec = outage.noteRawGps(t, lat, lon, feed, estimateAtRestore)
        gpsTrail.addLast(GeoPoint(t, lat, lon))
        while (gpsTrail.size > 400) gpsTrail.removeFirst()
        _state.update {
            it.copy(
                rawGps = RawGpsView(lat, lon, speedMps, hasSpeed, accuracyM),
                lastOutage = rec ?: it.lastOutage,
                outageHistory = outage.history,
                gpsTrail = gpsTrail.toList()
            )
        }
        refreshMode()
    }

    fun onPoll(snapshot: NavSnapshot?, diagnostics: EngineDiagnostics, v2v: V2vSnapshot?, approaching: Boolean) {
        val sim = _state.value.simulateOutage
        if (snapshot != null) {
            outage.noteEstimate(snapshot.timestamp, snapshot.lat, snapshot.lon, snapshot.isDeadReckoning, sim)
            estTrail.addLast(GeoPoint(snapshot.timestamp, snapshot.lat, snapshot.lon))
            while (estTrail.size > 400) estTrail.removeFirst()
        }
        val mapBad = snapshot?.mapStatus?.contains("NOT AVAILABLE", true) == true
        _state.update {
            it.copy(
                snapshot = snapshot,
                diagnostics = diagnostics,
                speedLabel = SpeedDisplay.formatKmh(snapshot?.speedMps ?: Double.NaN, snapshot?.speedValid == true),
                mapUnavailable = mapBad,
                outageLive = outage.inOutage,
                outageDurationS = outage.liveDurationS,
                outageHistory = outage.history,
                estimateTrail = estTrail.toList(),
                v2v = v2v,
                approachingBoundary = approaching,
                activeRegionId = snapshot?.regionId.orEmpty()
            )
        }
        refreshMode()
    }

    private fun refreshMode() {
        val s = _state.value
        val mode = NavModeResolver.resolve(
            engineError = s.engineError,
            initialized = s.initialized,
            replay = s.replayActive,
            experiment = s.experimentActive,
            simulateOutage = s.simulateOutage,
            hasRawGps = s.rawGps != null,
            snapshot = s.snapshot,
            mapUnavailable = s.mapUnavailable
        )
        _state.update { it.copy(mode = mode) }
    }
}
