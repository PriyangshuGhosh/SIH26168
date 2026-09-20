package com.vizag.nav.ui

import android.content.Context
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import com.vizag.nav.AppTheme
import com.vizag.nav.NavMode
import com.vizag.nav.NavState
import com.vizag.nav.R
import com.vizag.nav.TravelMode
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline
import org.osmdroid.views.overlay.TilesOverlay
import org.osmdroid.views.overlay.gestures.RotationGestureOverlay

// Google Maps Dark Theme Colors
val GmDarkBg = Color(0xFF202124)
val GmDarkSurface = Color(0xFF303134)
val GmTextPrimary = Color(0xFFE8EAED)
val GmTextSecondary = Color(0xFF9AA0A6)
val GpsGreen = Color(0xFF1E8E3E)
val DrRed = Color(0xFFD93025)

fun calculateDistanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Float {
    val results = FloatArray(1)
    android.location.Location.distanceBetween(lat1, lon1, lat2, lon2, results)
    return results[0]
}

@Composable
fun MapScreen(
    state: NavState,
    simulateOutage: Boolean,
    onToggleOutage: () -> Unit,
    onUpdateState: (NavState) -> Unit,
    context: Context
) {
    var showSettings by remember { mutableStateOf(false) }

    if (showSettings) {
        SettingsScreen(
            state = state,
            onUpdateState = onUpdateState,
            onClose = { showSettings = false }
        )
        return
    }

    Box(Modifier.fillMaxSize().background(if (state.theme == AppTheme.DARK_BLUE) GmDarkBg else Color.White)) {
        
        OsmMapView(state = state, context = context, modifier = Modifier.fillMaxSize(), onUpdateState = onUpdateState)

        TopRoutingBar(
            state = state,
            onUpdateDestination = { onUpdateState(state.copy(destination = it)) },
            onOpenSettings = { showSettings = true }
        )

        BottomStatusBar(
            state = state,
            simulateOutage = simulateOutage,
            onToggleOutage = onToggleOutage,
            onUpdateState = onUpdateState,
            modifier = Modifier.align(Alignment.BottomCenter)
        )
    }
}

@Composable
fun TopRoutingBar(
    state: NavState,
    onUpdateDestination: (String) -> Unit,
    onOpenSettings: () -> Unit
) {
    val isDark = state.theme == AppTheme.DARK_BLUE
    val surfaceColor = if (isDark) GmDarkSurface else Color.White
    val textColor = if (isDark) GmTextPrimary else Color.Black
    val hintColor = if (isDark) GmTextSecondary else Color.Gray

    Surface(
        modifier = Modifier.fillMaxWidth().padding(16.dp).padding(top = 24.dp),
        shape = RoundedCornerShape(12.dp),
        color = surfaceColor,
        shadowElevation = 8.dp
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Box(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                        .background(if (isDark) GmDarkBg else Color(0xFFF1F3F4))
                        .padding(12.dp)
                ) {
                    Text("Your location", color = textColor, fontSize = 14.sp)
                }
                Spacer(Modifier.height(8.dp))
                Box(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                        .background(if (isDark) GmDarkBg else Color(0xFFF1F3F4))
                        .padding(12.dp)
                ) {
                    Text(state.destination.ifEmpty { "Choose destination..." }, color = hintColor, fontSize = 14.sp)
                }
            }
            Spacer(Modifier.width(16.dp))
            Box(
                Modifier.size(40.dp).clip(CircleShape)
                    .background(if (isDark) Color(0xFF8AB4F8) else Color(0xFF1A73E8))
                    .clickable { onOpenSettings() },
                contentAlignment = Alignment.Center
            ) {
                Text("S", color = Color.White, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
fun BottomStatusBar(
    state: NavState,
    simulateOutage: Boolean,
    onToggleOutage: () -> Unit,
    onUpdateState: (NavState) -> Unit,
    modifier: Modifier = Modifier
) {
    val isSearching = state.lastGpsFix == 0L && !simulateOutage
    val isGpsActive = !simulateOutage && !state.isGpsStale && !isSearching
    
    val topColor = when {
        isGpsActive -> GpsGreen
        isSearching -> Color(0xFFFABB05)
        else -> DrRed
    }
    
    val statusText = when {
        simulateOutage -> "Dead Reckoning (Simulated)"
        isSearching -> "Searching for GPS..."
        state.isGpsStale -> "Dead Reckoning (GPS Lost)"
        else -> "GPS Active"
    }

    val isDark = state.theme == AppTheme.DARK_BLUE

    Surface(
        color = if (isDark) GmDarkSurface else Color.White,
        shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp),
        shadowElevation = 16.dp,
        modifier = modifier.fillMaxWidth().navigationBarsPadding()
    ) {
        Column {
            Box(Modifier.fillMaxWidth().height(4.dp).background(topColor))
            
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Row(modifier = Modifier.padding(bottom = 8.dp)) {
                        ModeChip("Vehicle", state.travelMode == TravelMode.VEHICLE) {
                            onUpdateState(state.copy(travelMode = TravelMode.VEHICLE))
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        ModeChip("Walk", state.travelMode == TravelMode.WALK) {
                            onUpdateState(state.copy(travelMode = TravelMode.WALK))
                        }
                    }
                
                    Text(text = statusText, color = topColor, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    
                    if (state.destinationPt != null) {
                        val distMeters = calculateDistanceMeters(state.lat, state.lon, state.destinationPt.first, state.destinationPt.second)
                        val distText = if (distMeters > 1000) String.format("%.1f km left", distMeters / 1000f) else "${distMeters.toInt()} m left"
                        Text(text = distText, color = Color(0xFF1A73E8), fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    } else if (state.travelMode == TravelMode.VEHICLE) {
                        Text(text = "ONNX Confidence: ${(state.speedConfidence * 100).toInt()}%", color = Color.Gray, fontSize = 12.sp)
                    } else {
                        Text("Pedometer mode active", color = Color.Gray, fontSize = 12.sp)
                    }
                }

                Column(horizontalAlignment = Alignment.End) {
                    val speedText = if (state.travelMode == TravelMode.VEHICLE) {
                        "${(state.speedMps * 3.6f).toInt()} km/h"
                    } else {
                        "${if (state.speedMps > 0) 110 else 0} steps/m"
                    }
                    Text(speedText, fontSize = 28.sp, fontWeight = FontWeight.Black, color = if (isDark) Color.White else Color.Black)
                    Text("${state.headingDeg.toInt()}° " + headingLabel(state.headingDeg), fontSize = 16.sp, color = Color.Gray)
                }
            }
            
            Button(
                onClick = onToggleOutage,
                modifier = Modifier.padding(horizontal = 16.dp).padding(bottom = 24.dp).fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = if (isDark) GmDarkBg else Color(0xFFF1F3F4))
            ) {
                Text(
                    if (simulateOutage) "Turn GPS Back On" else "Simulate GPS Outage",
                    color = if (simulateOutage) GpsGreen else DrRed,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}

@Composable
fun ModeChip(text: String, isSelected: Boolean, onClick: () -> Unit) {
    Surface(
        color = if (isSelected) Color(0xFF1A73E8) else Color(0xFFE8EAED),
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.clickable { onClick() }
    ) {
        Text(
            text = text,
            color = if (isSelected) Color.White else Color.DarkGray,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
fun SettingsScreen(state: NavState, onUpdateState: (NavState) -> Unit, onClose: () -> Unit) {
    val isDark = state.theme == AppTheme.DARK_BLUE
    val bg = if (isDark) GmDarkBg else Color.White
    val textC = if (isDark) GmTextPrimary else Color.Black

    Column(Modifier.fillMaxSize().background(bg).padding(24.dp)) {
        Text("Settings & Dev Options", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = textC)
        Spacer(Modifier.height(24.dp))

        Text("Theme", fontWeight = FontWeight.SemiBold, color = textC)
        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
            Button(onClick = { onUpdateState(state.copy(theme = AppTheme.LIGHT)) }, colors = ButtonDefaults.buttonColors(containerColor = if (isDark) GmDarkSurface else Color(0xFF1A73E8))) { Text("Light", color = Color.White) }
            Button(onClick = { onUpdateState(state.copy(theme = AppTheme.DARK_BLUE)) }, colors = ButtonDefaults.buttonColors(containerColor = if (isDark) Color(0xFF8AB4F8) else Color.Gray)) { Text("Dark Maps", color = Color.White) }
        }

        Spacer(Modifier.height(32.dp))

        Text("Dev Options (Repo Integration Status)", fontWeight = FontWeight.SemiBold, color = textC, fontSize = 18.sp)
        Spacer(Modifier.height(8.dp))
        DevStatusRow("GPS Signal Available", state.isGnssActive, isDark)
        DevStatusRow("IMU Hardware Sensor (100Hz)", state.isImuActive, isDark)
        DevStatusRow("ONNX ML Engine (final.production.onnx)", state.isOnnxReady, isDark)

        Spacer(Modifier.height(16.dp))
        Text("Dashboard / Member Logs", fontWeight = FontWeight.SemiBold, color = textC, fontSize = 18.sp)
        Box(Modifier.weight(1f).fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(if(isDark) GmDarkSurface else Color(0xFFF1F3F4)).padding(8.dp)) {
            LazyColumn {
                items(state.dashboardLogs) { log ->
                    Text(log, color = if(isDark) Color.LightGray else Color.DarkGray, fontSize = 11.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
                    Divider(color = Color.Gray.copy(alpha=0.3f), modifier = Modifier.padding(vertical=4.dp))
                }
            }
        }

        Spacer(Modifier.height(16.dp))
        Button(onClick = onClose, modifier = Modifier.fillMaxWidth()) { Text("Close Settings") }
    }
}
@Composable
fun DevStatusRow(label: String, isActive: Boolean, isDark: Boolean) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(12.dp).clip(CircleShape).background(if (isActive) GpsGreen else DrRed))
        Spacer(Modifier.width(12.dp))
        Text(label, color = if (isDark) GmTextPrimary else Color.Black)
    }
}

@Composable
private fun OsmMapView(state: NavState, context: Context, modifier: Modifier = Modifier, onUpdateState: ((NavState) -> Unit)? = null) {
    val mapViewRef = remember { mutableStateOf<MapView?>(null) }
    val markerRef  = remember { mutableStateOf<Marker?>(null) }
    val destMarkerRef = remember { mutableStateOf<Marker?>(null) }
    val routePolyRef = remember { mutableStateOf<Polyline?>(null) }

    LaunchedEffect(state.lat, state.lon, state.headingDeg, state.theme, state.destinationPt) {
        val mv = mapViewRef.value ?: return@LaunchedEffect
        val mk = markerRef.value ?: return@LaunchedEffect
        val destMk = destMarkerRef.value ?: return@LaunchedEffect
        
        if (state.theme == AppTheme.DARK_BLUE) {
            val filter = android.graphics.ColorMatrix(floatArrayOf(
                -1f, 0f, 0f, 0f, 255f,
                0f, -1f, 0f, 0f, 255f,
                0f, 0f, -1f, 0f, 255f,
                0f, 0f, 0f, 1f, 0f
            ))
            mv.overlayManager.tilesOverlay.setColorFilter(android.graphics.ColorMatrixColorFilter(filter))
        } else {
            mv.overlayManager.tilesOverlay.setColorFilter(null)
        }

        val pos = GeoPoint(state.lat, state.lon)
        mk.position = pos
        mk.rotation = -state.headingDeg
        
        if (state.destinationPt != null) {
            val destPos = GeoPoint(state.destinationPt.first, state.destinationPt.second)
            destMk.position = destPos
            destMk.setAlpha(1f)
            
            if (state.travelMode == TravelMode.VEHICLE) {
                kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                    try {
                        val urlStr = "https://router.project-osrm.org/route/v1/driving/${state.lon},${state.lat};${state.destinationPt.second},${state.destinationPt.first}?overview=full&geometries=geojson"
                        val conn = java.net.URL(urlStr).openConnection() as java.net.HttpURLConnection
                        val response = conn.inputStream.bufferedReader().readText()
                        val json = org.json.JSONObject(response)
                        val routes = json.getJSONArray("routes")
                        if (routes.length() > 0) {
                            val geometry = routes.getJSONObject(0).getJSONObject("geometry")
                            val coords = geometry.getJSONArray("coordinates")
                            val points = mutableListOf<GeoPoint>()
                            for (i in 0 until coords.length()) {
                                val pt = coords.getJSONArray(i)
                                points.add(GeoPoint(pt.getDouble(1), pt.getDouble(0)))
                            }
                            withContext(kotlinx.coroutines.Dispatchers.Main) {
                                routePolyRef.value?.setPoints(points)
                                mv.invalidate()
                            }
                        }
                    } catch (e: Exception) {
                        e.printStackTrace()
                        withContext(kotlinx.coroutines.Dispatchers.Main) {
                            routePolyRef.value?.setPoints(listOf(pos, destPos))
                            mv.invalidate()
                        }
                    }
                }
            } else {
                routePolyRef.value?.setPoints(listOf(pos, destPos))
            }
        } else {
            destMk.setAlpha(0f)
            routePolyRef.value?.setPoints(emptyList())
        }

        mv.invalidate()
        if (!mv.isAnimating) mv.controller.animateTo(pos, 18.5, 500L)
    }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            Configuration.getInstance().apply {
                userAgentValue = "VizagNav/1.0"
                osmdroidBasePath = ctx.filesDir
                osmdroidTileCache = ctx.cacheDir.resolve("osmdroid_tiles")
            }
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
                isTilesScaledToDpi = true
                overlays.add(RotationGestureOverlay(this).also { it.isEnabled = true })

                val mReceive = object : org.osmdroid.events.MapEventsReceiver {
                    override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                        onUpdateState?.invoke(state.copy(
                            destinationPt = Pair(p.latitude, p.longitude),
                            destination = "Pin at ${String.format("%.4f", p.latitude)}, ${String.format("%.4f", p.longitude)}"
                        ))
                        return true
                    }
                    override fun longPressHelper(p: GeoPoint): Boolean = false
                }
                overlays.add(org.osmdroid.views.overlay.MapEventsOverlay(mReceive))

                controller.setZoom(18.5)
                controller.setCenter(GeoPoint(NavState.VIZAG_CENTER_LAT, NavState.VIZAG_CENTER_LON))

                val routeLine = Polyline(this).apply { 
                    outlinePaint.color = android.graphics.Color.argb(200, 52, 168, 83)
                    outlinePaint.strokeWidth = 12f 
                }

                val destMarker = Marker(this).apply {
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    icon = resources.getDrawable(org.osmdroid.library.R.drawable.marker_default, null)
                    setAlpha(0f)
                    infoWindow = null
                }

                val marker = Marker(this).apply {
                    position = GeoPoint(state.lat, state.lon)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                    icon = resources.getDrawable(R.drawable.nav_arrow, null)
                    infoWindow = null
                }

                overlays.add(routeLine)
                overlays.add(destMarker)
                overlays.add(marker)
                
                routePolyRef.value = routeLine
                destMarkerRef.value = destMarker
                markerRef.value = marker
                mapViewRef.value = this
            }
        }
    )
}

fun headingLabel(deg: Float): String {
    val normalized = ((deg % 360) + 360) % 360
    return when {
        normalized < 22.5 || normalized >= 337.5 -> "N"
        normalized < 67.5 -> "NE"
        normalized < 112.5 -> "E"
        normalized < 157.5 -> "SE"
        normalized < 202.5 -> "S"
        normalized < 247.5 -> "SW"
        normalized < 292.5 -> "W"
        else -> "NW"
    }
}
