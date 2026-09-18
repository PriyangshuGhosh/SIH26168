package com.example.member6app

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.example.member6app.navigation.NavigationViewModel
import com.example.member6app.theme.Member6AppTheme
import com.example.member6app.ui.NavigationScreen
import com.example.member6app.ui.PermissionGate

/**
 * MainActivity — single-activity app.
 *
 * Lifecycle contract:
 *   onCreate  → setContent (Compose tree, permission gate)
 *   onResume  → sensor/GNSS restart
 *   onPause   → sensor/GNSS stop (camera managed by lifecycle-aware CameraService)
 *   onDestroy → ViewModel.onCleared() shuts down engine automatically
 *
 * Native engine lifecycle:
 *   Initialized in NavigationViewModel after permissions are confirmed.
 *   Destroyed in ViewModel.onCleared() (called by Android when activity is
 *   permanently destroyed, not on rotation). This prevents double-init on
 *   screen rotation.
 *
 * Map / ONNX paths:
 *   "" is passed during development to let the engine start in stub mode.
 *   Replace with actual asset paths when files are available.
 */
class MainActivity : ComponentActivity() {

    private val viewModel: NavigationViewModel by viewModels()

    companion object {
        private const val TAG = "MainActivity"
        // For the demo, we push these files into the app's external files directory:
        // C:\Users\anish\AppData\Local\Android\Sdk\platform-tools\adb.exe push member4_map_matching\data\vizag.roadpack /sdcard/Android/data/com.example.member6app/files/
        // C:\Users\anish\AppData\Local\Android\Sdk\platform-tools\adb.exe push final.production.onnx /sdcard/Android/data/com.example.member6app/files/
        const val MAP_DB_PATH = "/sdcard/Android/data/com.example.member6app/files/vizag.roadpack"
        const val ONNX_MODEL_PATH = "/sdcard/Android/data/com.example.member6app/files/final.production.onnx"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            Member6AppTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    // PermissionGate ensures permissions are granted before
                    // sensors or engine start
                    PermissionGate {
                        // Permissions are granted — init engine + sensors once.
                        // startSensors() is also called here so sensors begin
                        // immediately when permissions are confirmed, without
                        // waiting for onResume which fires before engine init.
                        androidx.compose.runtime.LaunchedEffect(Unit) {
                            viewModel.startSensors()
                            viewModel.initEngine(MAP_DB_PATH, ONNX_MODEL_PATH)
                        }
                        NavigationScreen(viewModel = viewModel)
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Always restart sensors on foreground — safe to call even before engine
        // init completes (ImuService/GnssService buffer independently).
        viewModel.startSensors()
        Log.i(TAG, "onResume — sensors restarted")
    }

    override fun onPause() {
        super.onPause()
        // Stop high-rate IMU and GNSS when backgrounded to save battery.
        // Navigation state is preserved in the native engine.
        viewModel.stopSensors()
        Log.i(TAG, "onPause — sensors stopped")
    }
}
