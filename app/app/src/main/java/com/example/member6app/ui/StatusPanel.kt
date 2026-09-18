package com.example.member6app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.member6app.navigation.NavigationMode
import com.example.member6app.navigation.NavigationUiState

/**
 * StatusPanel — displays navigation mode, speed, heading, confidence.
 * Designed for the main judging screen. Judge-friendly colors and labels.
 */
@Composable
fun StatusPanel(
    state: NavigationUiState,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier.padding(horizontal = 8.dp, vertical = 4.dp)) {
        // Mode row
        ModeRow(state)
        Spacer(Modifier.height(6.dp))

        // Speed / Heading row
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            MetricCard(label = "SPEED", value = "%.1f km/h".format(state.speedKmh))
            MetricCard(label = "HEADING", value = "%.1f°".format(state.headingDeg))
        }

        Spacer(Modifier.height(6.dp))

        // GNSS / Confidence row
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            MetricCard(label = "GNSS", value = state.gnssLabel, color = gnssColor(state))
            MetricCard(
                label = "CONFIDENCE",
                value = "%.2f".format(state.confidence),
                color = confidenceColor(state.confidence)
            )
        }

        Spacer(Modifier.height(4.dp))

        // Position row
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            Text(
                text = if (state.latitude != 0.0 || state.longitude != 0.0)
                    "%.6f, %.6f".format(state.latitude, state.longitude)
                else "No position",
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        // Engine error banner
        if (state.mode == NavigationMode.ENGINE_FAILED && state.engineError.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            Surface(color = MaterialTheme.colorScheme.errorContainer, shape = RoundedCornerShape(4.dp)) {
                Text(
                    text = "ENGINE: ${state.engineError}",
                    modifier = Modifier.padding(8.dp),
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    style = MaterialTheme.typography.labelSmall,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
    }
}

@Composable
private fun ModeRow(state: NavigationUiState) {
    val bgColor = when (state.mode) {
        NavigationMode.GNSS_AIDED       -> Color(0xFF1B5E20)  // dark green
        NavigationMode.DEAD_RECKONING   -> Color(0xFFE65100)  // deep orange
        NavigationMode.GNSS_OUTAGE_SIM  -> Color(0xFFB71C1C)  // dark red
        NavigationMode.INITIALIZING     -> Color(0xFF1A237E)  // dark blue
        NavigationMode.ENGINE_FAILED    -> Color(0xFF880E4F)  // dark magenta
        NavigationMode.NO_FIX           -> Color(0xFF37474F)  // blue-grey
    }
    Surface(
        color = bgColor,
        shape = RoundedCornerShape(6.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = state.modeLabel,
                color = Color.White,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            if (state.mode == NavigationMode.GNSS_OUTAGE_SIM) {
                Text(
                    text = "DEMO — SIMULATED OUTAGE",
                    color = Color(0xFFFFCC02),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold
                )
            }
            Text(
                text = "SENSOR: ${state.sensorMode.name}",
                color = Color.White.copy(alpha = 0.7f),
                style = MaterialTheme.typography.labelSmall
            )
        }
    }
}

@Composable
private fun MetricCard(label: String, value: String, color: Color = Color.Unspecified) {
    Card(
        modifier = Modifier
            .widthIn(min = 140.dp)
            .padding(4.dp)
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(label, style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(2.dp))
            Text(
                text = value,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp,
                color = if (color != Color.Unspecified) color else MaterialTheme.colorScheme.onSurface,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

private fun gnssColor(state: NavigationUiState): Color = when {
    state.mode == NavigationMode.GNSS_AIDED      -> Color(0xFF2E7D32)
    state.mode == NavigationMode.GNSS_OUTAGE_SIM -> Color(0xFFC62828)
    !state.gnssAvailable                          -> Color(0xFF757575)
    else                                           -> Color(0xFFE65100)
}

private fun confidenceColor(c: Double): Color = when {
    c >= 0.7 -> Color(0xFF2E7D32)
    c >= 0.4 -> Color(0xFFE65100)
    else     -> Color(0xFFC62828)
}
