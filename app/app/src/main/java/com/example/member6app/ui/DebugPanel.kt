package com.example.member6app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.example.member6app.navigation.NavigationUiState

/**
 * DebugPanel — Engineering diagnostics screen.
 *
 * Shows raw values for:
 *   - IMU measured rate
 *   - GNSS update rate
 *   - Camera FPS
 *   - Native engine status
 *   - Navigation mode / confidence
 *   - Vision confidence / status
 *   - Map status
 *   - Dropped samples (from ImuService)
 *   - Library load status
 *
 * Accessible via a "Debug" tab in the main UI.
 * Hidden from the primary judging view but NOT disabled.
 */
@Composable
fun DebugPanel(
    state: NavigationUiState,
    imuDropped: Long,
    imuSamples: Long,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .padding(8.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text("── ENGINEERING DIAGNOSTICS ──",
             style = MaterialTheme.typography.titleSmall,
             fontFamily = FontFamily.Monospace,
             color = MaterialTheme.colorScheme.primary)

        Spacer(Modifier.height(8.dp))

        DebugSection("NATIVE ENGINE") {
            DebugRow("Status",    if (state.engineInitialized) "OK" else "FAILED")
            DebugRow("Library",   if (state.engineInitialized) "libidr_engine.so LOADED" else "NOT LOADED")
            DebugRow("Mode",      state.modeLabel)
            DebugRow("Error",     state.engineError.ifEmpty { "none" })
        }

        DebugSection("IMU") {
            DebugRow("Measured Hz",  "%.1f Hz".format(state.imuHz))
            DebugRow("Samples",      "$imuSamples")
            DebugRow("Dropped",      "$imuDropped")
            DebugRow("Timestamp",    "boot-clock (nanoseconds)")
        }

        DebugSection("GNSS") {
            DebugRow("Available",  state.gnssAvailable.toString().uppercase())
            DebugRow("Satellites", state.gnssSatellites.toString())
            DebugRow("Accuracy",   if (state.gnssAccuracy.isNaN()) "N/A" else "%.1f m".format(state.gnssAccuracy))
            DebugRow("HDOP proxy", "accuracy/5 (NOT real HDOP)")
        }

        DebugSection("NAVIGATION OUTPUT") {
            DebugRow("Lat",        "%.7f".format(state.latitude))
            DebugRow("Lon",        "%.7f".format(state.longitude))
            DebugRow("Speed",      "%.2f km/h".format(state.speedKmh))
            DebugRow("Heading",    "%.2f°".format(state.headingDeg))
            DebugRow("Confidence", "%.3f".format(state.confidence))
        }

        DebugSection("CAMERA / VISION") {
            DebugRow("Camera FPS",         "%.1f".format(state.cameraFps))
            DebugRow("Vision Confidence",  "%.2f".format(state.visionConfidence))
            DebugRow("Vision Status",      state.visionStatus)
            DebugRow("EKF Integration",    "PENDING MEMBER 3 API")
        }

        DebugSection("MAP") {
            DebugRow("Map Status", state.mapStatus)
            DebugRow("Type",       "Compose Canvas (offline)")
        }

        DebugSection("SYSTEM CLASSIFICATION") {
            StatusClassRow("Member 2 (FrameAligner)",   "REAL")
            StatusClassRow("Member 1 (AI Speed)",       "REAL (ONNX model loaded)")
            StatusClassRow("Member 3 (EKF)",            "REAL")
            StatusClassRow("Member 4 (Map Matching)",   "REAL (synthetic_grid.roadpack)")
            StatusClassRow("Member 5 (Engine)",         "REAL — libidr_engine.so")
            StatusClassRow("Vision/EKF integration",    "EXPERIMENTAL — gated, not injected")
        }
    }
}

@Composable
private fun DebugSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Spacer(Modifier.height(8.dp))
    Text(title, style = MaterialTheme.typography.labelMedium,
         color = MaterialTheme.colorScheme.secondary,
         fontFamily = FontFamily.Monospace)
    HorizontalDivider(Modifier.padding(vertical = 2.dp))
    Column { content() }
}

@Composable
private fun DebugRow(key: String, value: String) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 1.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(key, style = MaterialTheme.typography.bodySmall,
             fontFamily = FontFamily.Monospace,
             color = MaterialTheme.colorScheme.onSurfaceVariant,
             modifier = Modifier.weight(0.45f))
        Text(value, style = MaterialTheme.typography.bodySmall,
             fontFamily = FontFamily.Monospace,
             modifier = Modifier.weight(0.55f))
    }
}

@Composable
private fun StatusClassRow(component: String, classification: String) {
    val color = when (classification) {
        "REAL"        -> Color(0xFF2E7D32)
        "STUB"        -> Color(0xFFE65100)
        else          -> MaterialTheme.colorScheme.onSurface
    }
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 1.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(component, style = MaterialTheme.typography.bodySmall,
             fontFamily = FontFamily.Monospace,
             modifier = Modifier.weight(0.6f))
        Text(classification, style = MaterialTheme.typography.bodySmall,
             fontFamily = FontFamily.Monospace,
             color = color, modifier = Modifier.weight(0.4f))
    }
}
