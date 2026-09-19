package org.sih26168.idr.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.sih26168.idr.NavUiState
import org.sih26168.idr.SpeedDisplay
import org.sih26168.idr.SpeedUnits
import org.sih26168.idr.label
import kotlin.math.cos
import kotlin.math.sin

private val Land = Color(0xFFE8EEF4)
private val RoadFill = Color(0xFFF7F4EC)
private val RoadEdge = Color(0xFFC4C0B4)
private val Teal = Color(0xFF0F6E6A)
private val GpsBlue = Color(0xFF2A6FBF)
private val DrOrange = Color(0xFFC45C26)
private val Ink = Color(0xFF1B2430)

@Composable
fun IdrTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Teal,
            background = Land,
            surface = Color.White,
            onSurface = Ink
        ),
        content = content
    )
}

@Composable
fun NavigationScreen(
    state: NavUiState,
    onToggleOutage: () -> Unit
) {
    Box(Modifier.fillMaxSize().background(Land)) {
        OfflineMapCanvas(state, Modifier.fillMaxSize())
        Column(Modifier.fillMaxSize()) {
            Surface(
                Modifier.fillMaxWidth().padding(12.dp),
                shape = RoundedCornerShape(24.dp),
                color = Color.White.copy(alpha = 0.94f),
                shadowElevation = 4.dp
            ) {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) {
                    Text("SIH26168 Offline Nav", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                    Text(state.mode.label(), color = Teal, fontWeight = FontWeight.Medium, fontSize = 13.sp)
                }
            }
            Spacer(Modifier.weight(1f))
            Surface(
                Modifier.fillMaxWidth().padding(12.dp),
                shape = RoundedCornerShape(20.dp),
                color = Color.White.copy(alpha = 0.96f),
                shadowElevation = 6.dp
            ) {
                Column(
                    Modifier.padding(16.dp).height(280.dp).verticalScroll(rememberScrollState())
                ) {
                    Text(state.speedLabel, fontSize = 28.sp, fontWeight = FontWeight.Bold)
                    Text(state.mode.label(), color = if (state.simulateOutage) DrOrange else Teal)
                    val s = state.snapshot
                    Text(
                        if (s == null) "Position unavailable" else
                            "Est ${"%.6f".format(s.lat)}, ${"%.6f".format(s.lon)}  hdg ${"%.0f".format(s.headingDeg)}°"
                    )
                    val gps = state.rawGps
                    Text(
                        if (gps == null) "Raw GNSS: none" else
                            "Raw GNSS ${"%.6f".format(gps.lat)}, ${"%.6f".format(gps.lon)}" +
                                if (gps.hasSpeed) "  ${"%.1f".format(SpeedUnits.mpsToKmh(gps.speedMps))} km/h raw"
                                else "  speed n/a"
                    )
                    Text("Validated speed: ${state.speedLabel}  (no silent clamp)")
                    if (state.mapUnavailable) Text("MAP DATA NOT AVAILABLE", color = DrOrange, fontWeight = FontWeight.Bold)
                    Text("Region ${state.activeRegionId.ifBlank { "—" }}")
                    Button(onClick = onToggleOutage, Modifier.fillMaxWidth().padding(top = 8.dp)) {
                        Text(if (state.simulateOutage) "Restore GNSS feed" else "Simulate GNSS outage")
                    }
                    EngineeringBlock(state)
                }
            }
        }
    }
}

@Composable
private fun EngineeringBlock(state: NavUiState) {
    val d = state.diagnostics
    Spacer(Modifier.height(8.dp))
    Text("Engineering", fontWeight = FontWeight.SemiBold)
    Text(
        "GNSS ${fmt(d.rawGnssSpeedMps)}  AI ${fmt(d.aiSpeedMps)}  EKF ${fmt(d.ekfSpeedMps)}  shown ${fmt(d.displayedSpeedMps)} m/s",
        fontFamily = FontFamily.Monospace,
        fontSize = 11.sp
    )
    Text("IMU ${fmt(d.imuHz)} Hz  reject ${state.snapshot?.speedRejectReason ?: "—"}", fontFamily = FontFamily.Monospace, fontSize = 11.sp)
    Text("Outage live=${state.outageLive}  ${"%.1f".format(state.outageDurationS)} s  history ${state.outageHistory.size}")
    state.lastOutage?.let {
        Text(
            "finalDriftMeters=${"%.2f".format(it.finalDriftMeters)} (est-at-restore vs restored GPS; not last-GPS vs new-GPS)",
            fontSize = 12.sp
        )
        it.gpsDisplacementDuringOutageMeters?.let { gap ->
            Text("GPS displacement during outage (not drift): ${"%.2f".format(gap)} m", fontSize = 11.sp)
        }
    }
    Text(state.hardwareNote, fontSize = 11.sp, color = DrOrange)
    Text(state.accuracyNote, fontSize = 11.sp, color = DrOrange)
    val v = state.v2v
    if (v != null) {
        Text("V2V ${v.libraryStatus} / ${v.androidAdapterStatus}", fontSize = 11.sp)
        Text("transport=${v.transport} remotes=${v.remotes.size} coop=${v.coopReason}", fontSize = 11.sp)
    }
    state.storage?.let {
        Text("Road data ${it.usedBytes} B / ${it.maxBytes} B  regions=${it.regionCount}", fontSize = 11.sp)
    }
    if (state.approachingBoundary) Text("Approaching region boundary — prefetch is host-side if internet exists.")
}

private fun fmt(x: Double): String = if (!x.isFinite()) "—" else "%.2f".format(x)

@Composable
private fun OfflineMapCanvas(state: NavUiState, modifier: Modifier) {
    Canvas(modifier) {
        val graph = state.roads
        val minLat = graph?.minLat ?: 12.9715
        val maxLat = graph?.maxLat ?: 12.9738
        val minLon = graph?.minLon ?: 77.5945
        val maxLon = graph?.maxLon ?: 77.5969
        fun xy(lat: Double, lon: Double): Offset {
            val x = ((lon - minLon) / (maxLon - minLon).coerceAtLeast(1e-9)).toFloat() * size.width
            val y = (1.0 - (lat - minLat) / (maxLat - minLat).coerceAtLeast(1e-9)).toFloat() * size.height
            return Offset(x, y)
        }
        drawRect(Land)
        graph?.polylines?.forEach { poly ->
            if (poly.points.size < 2) return@forEach
            val path = Path()
            val first = xy(poly.points[0].first, poly.points[0].second)
            path.moveTo(first.x, first.y)
            for (i in 1 until poly.points.size) {
                val p = xy(poly.points[i].first, poly.points[i].second)
                path.lineTo(p.x, p.y)
            }
            drawPath(path, RoadEdge, style = Stroke(width = 10f, cap = StrokeCap.Round))
            drawPath(path, RoadFill, style = Stroke(width = 6f, cap = StrokeCap.Round))
        }
        fun trail(points: List<org.sih26168.idr.GeoPoint>, color: Color) {
            if (points.size < 2) return
            val path = Path()
            val a = xy(points.first().lat, points.first().lon)
            path.moveTo(a.x, a.y)
            points.drop(1).forEach { path.lineTo(xy(it.lat, it.lon).x, xy(it.lat, it.lon).y) }
            drawPath(path, color, style = Stroke(width = 4f))
        }
        trail(state.gpsTrail, GpsBlue)
        trail(state.estimateTrail, DrOrange)
        state.rawGps?.let { drawCircle(GpsBlue, 10f, xy(it.lat, it.lon)) }
        state.snapshot?.let { snap ->
            val c = xy(snap.lat, snap.lon)
            val h = Math.toRadians(snap.headingDeg)
            val tip = Offset(c.x + (18f * sin(h)).toFloat(), c.y - (18f * cos(h)).toFloat())
            drawCircle(Teal, 14f, c)
            drawLine(Color.White, c, tip, strokeWidth = 4f)
        }
        state.v2v?.remotes?.forEach { r ->
            drawCircle(Color(0xFF7A4E9E), 8f, xy(r.lat, r.lon))
        }
    }
}
