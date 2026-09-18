package com.example.member6app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.member6app.navigation.NavigationViewModel

/**
 * NavigationScreen — Main judging UI.
 *
 * Layout:
 *   ┌─────────────────────────────────────┐
 *   │  SIH26168 NAVIGATION    [Debug tab] │
 *   ├─────────────────────────────────────┤
 *   │         OFFLINE MAP                 │  ← 55% height
 *   │              🚗                     │
 *   ├─────────────────────────────────────┤
 *   │     STATUS PANEL                    │  ← 30% height
 *   ├─────────────────────────────────────┤
 *   │  [SIMULATE GNSS OUTAGE]  [RESET]    │  ← controls
 *   └─────────────────────────────────────┘
 *
 * The Debug tab reveals DebugPanel without leaving this screen.
 */
@Composable
fun NavigationScreen(viewModel: NavigationViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val imuDiag = viewModel.imuService.diagnostics()
    var showDebug by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        if (state.simulation) {
            Surface(color = Color(0xFFB71C1C), modifier = Modifier.fillMaxWidth()) {
                Text(
                    "SIMULATION",
                    color = Color.White,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                    style = MaterialTheme.typography.labelLarge
                )
            }
        }
        if (state.mapMessage.contains("unavailable", ignoreCase = true) ||
            state.mapStatus.contains("NOT AVAILABLE")
        ) {
            Surface(color = Color(0xFF37474F), modifier = Modifier.fillMaxWidth()) {
                Text(
                    "Offline map unavailable for this area",
                    color = Color.White,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                    style = MaterialTheme.typography.labelMedium
                )
            }
        }
        TopBar(showDebug = showDebug, onToggleDebug = { showDebug = !showDebug })

        // ── Map or Debug ──────────────────────────────────────────────────────
        Box(
            Modifier
                .fillMaxWidth()
                .weight(0.55f)
        ) {
            if (!showDebug) {
                OfflineMapView(
                    latitude   = state.latitude,
                    longitude  = state.longitude,
                    headingDeg = state.headingDeg,
                    modifier   = Modifier.fillMaxSize()
                )
            } else {
                DebugPanel(
                    state       = state,
                    imuDropped  = imuDiag.droppedEvents,
                    imuSamples  = imuDiag.sampleCount,
                    modifier    = Modifier.fillMaxSize()
                )
            }
        }

        HorizontalDivider()

        // ── Status Panel ──────────────────────────────────────────────────────
        StatusPanel(
            state    = state,
            modifier = Modifier
                .fillMaxWidth()
                .weight(0.32f)
        )

        HorizontalDivider()

        // ── Demo Controls ─────────────────────────────────────────────────────
        DemoControls(
            isOutageActive = viewModel.isGnssOutageSimulated,
            onToggleOutage = { active -> viewModel.simulateGnssOutage(active) },
            onReset        = { viewModel.resetNavigation() },
            modifier       = Modifier
                .fillMaxWidth()
                .padding(8.dp)
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TopBar(showDebug: Boolean, onToggleDebug: () -> Unit) {
    TopAppBar(
        title = { Text("SIH26168 NAVIGATION", style = MaterialTheme.typography.titleMedium) },
        actions = {
            IconButton(onClick = onToggleDebug) {
                Icon(
                    imageVector = if (showDebug) Icons.Default.Map else Icons.Default.BugReport,
                    contentDescription = if (showDebug) "Show Map" else "Show Debug"
                )
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    )
}

@Composable
private fun DemoControls(
    isOutageActive: Boolean,
    onToggleOutage: (Boolean) -> Unit,
    onReset: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // SIMULATE GNSS OUTAGE — prominent red/green toggle
        Button(
            onClick = { onToggleOutage(!isOutageActive) },
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isOutageActive) Color(0xFFC62828) else Color(0xFF1B5E20)
            ),
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.weight(1f)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (isOutageActive) {
                    Icon(Icons.Default.Warning, "Outage active", tint = Color.Yellow,
                         modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("RESTORE GNSS", style = MaterialTheme.typography.labelMedium)
                } else {
                    Text("SIMULATE GNSS OUTAGE", style = MaterialTheme.typography.labelMedium)
                }
            }
        }

        // RESET NAVIGATION
        OutlinedButton(
            onClick = onReset,
            modifier = Modifier.wrapContentWidth()
        ) {
            Text("RESET", style = MaterialTheme.typography.labelSmall)
        }
    }
}
