package com.example.member6app.ui

import android.Manifest
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.isGranted
import com.google.accompanist.permissions.rememberMultiplePermissionsState
import com.google.accompanist.permissions.shouldShowRationale

val REQUIRED_PERMISSIONS = listOf(
    Manifest.permission.ACCESS_FINE_LOCATION,
    Manifest.permission.CAMERA
)

/**
 * PermissionGate — wraps content behind permission checks.
 * Explains WHY each permission is needed before requesting.
 * Never crashes on denial; shows a clear fallback UI.
 */
@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun PermissionGate(
    content: @Composable () -> Unit
) {
    val permissionsState = rememberMultiplePermissionsState(REQUIRED_PERMISSIONS)

    if (permissionsState.allPermissionsGranted) {
        content()
    } else {
        val revokedPermissions = permissionsState.revokedPermissions
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("SIH26168 Navigation", style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.height(16.dp))
            Text(
                "This app requires the following permissions to operate:",
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(12.dp))

            val locationRevoked = revokedPermissions.any { it.permission == Manifest.permission.ACCESS_FINE_LOCATION }
            val cameraRevoked   = revokedPermissions.any { it.permission == Manifest.permission.CAMERA }

            if (locationRevoked) {
                PermissionItem(
                    title  = "Fine Location (GPS)",
                    reason = "Required to capture GNSS position for navigation. " +
                             "Without this, the app cannot demonstrate GNSS → Dead Reckoning transitions."
                )
            }
            if (cameraRevoked) {
                PermissionItem(
                    title  = "Camera",
                    reason = "Required for the auxiliary visual-confidence pipeline. " +
                             "Navigation continues without camera, but the vision pipeline will be disabled."
                )
            }

            Spacer(Modifier.height(24.dp))

            // Check if permanently denied (user clicked "Don't ask again")
            val anyPermanentlyDenied = revokedPermissions.any { !it.status.shouldShowRationale }

            if (anyPermanentlyDenied) {
                Text(
                    "Some permissions were permanently denied. Please enable them in device Settings → Apps → SIH26168 → Permissions.",
                    color = MaterialTheme.colorScheme.error,
                    textAlign = TextAlign.Center
                )
            } else {
                Button(onClick = { permissionsState.launchMultiplePermissionRequest() }) {
                    Text("Grant Permissions")
                }
            }
        }
    }
}

@Composable
private fun PermissionItem(title: String, reason: String) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
    ) {
        Column(Modifier.padding(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text(reason, style = MaterialTheme.typography.bodySmall)
        }
    }
}
