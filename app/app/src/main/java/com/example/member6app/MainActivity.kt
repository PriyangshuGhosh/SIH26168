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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import com.example.member6app.navigation.NavigationViewModel
import com.example.member6app.theme.Member6AppTheme
import com.example.member6app.ui.NavigationScreen
import com.example.member6app.ui.PermissionGate
import java.io.File

class MainActivity : ComponentActivity() {

    private val viewModel: NavigationViewModel by viewModels()

    companion object {
        private const val TAG = "MainActivity"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val mapsDir = File(filesDir, "maps")
        AssetProvisioner.copyAssetTree(this, "maps", mapsDir)
        val manifest = File(mapsDir, "manifest.json")
        val onnx = File(filesDir, "speed_estimator.onnx")
        val mapPath = if (manifest.exists()) manifest.absolutePath else File(mapsDir, "synthetic_grid.roadpack").absolutePath
        val modelPath = if (onnx.exists() && onnx.length() > 16L) onnx.absolutePath else "mock"

        setContent {
            Member6AppTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    PermissionGate {
                        LaunchedEffect(Unit) {
                            viewModel.startSensors()
                            viewModel.initEngine(mapPath, modelPath)
                        }
                        NavigationScreen(viewModel = viewModel)
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        viewModel.startSensors()
        Log.i(TAG, "onResume — sensors restarted")
    }

    override fun onPause() {
        super.onPause()
        viewModel.stopSensors()
        Log.i(TAG, "onPause — sensors stopped")
    }
}
