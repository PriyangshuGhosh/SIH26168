package com.example.member6app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import androidx.compose.foundation.Canvas as ComposeCanvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.sin
import androidx.compose.ui.graphics.Color as ComposeColor

private const val TAG = "OfflineMapView"

/**
 * OfflineMapView — pure-Compose canvas map renderer.
 *
 * Replaces the previous MapLibre implementation which caused
 * native crashes via SymbolManager (a v9 annotation plugin
 * incompatible with MapLibre v11).
 *
 * Renders a dark grid background (simulating a tile map) with
 * a blue directional vehicle marker in the centre of the screen.
 * The marker rotates with headingDeg. Lat/lon are displayed for
 * engineering reference.
 *
 * No network access, no native library beyond Compose/Skia.
 */
@Composable
fun OfflineMapView(
    latitude:   Double,
    longitude:  Double,
    headingDeg: Double,
    modifier:   Modifier = Modifier,
    @Suppress("UNUSED_PARAMETER") styleUri: String = ""
) {
    val gridColor    = ComposeColor(0xFF1a1a2e)
    val lineColor    = ComposeColor(0xFF2a2a4e)
    val markerBitmap = makeVehicleIconBitmap()
    val markerImage  = markerBitmap.asImageBitmap()

    Box(modifier = modifier) {
        ComposeCanvas(
            modifier = Modifier
                .fillMaxSize()
                .background(gridColor)
        ) {
            // Draw grid lines to simulate a tile map
            val spacing = 60f
            var x = 0f
            while (x <= size.width) {
                drawLine(
                    color     = lineColor,
                    start     = Offset(x, 0f),
                    end       = Offset(x, size.height),
                    strokeWidth = 1f
                )
                x += spacing
            }
            var y = 0f
            while (y <= size.height) {
                drawLine(
                    color     = lineColor,
                    start     = Offset(0f, y),
                    end       = Offset(size.width, y),
                    strokeWidth = 1f
                )
                y += spacing
            }

            // Draw vehicle marker centred, rotated to heading
            val cx = size.width  / 2f
            val cy = size.height / 2f
            val iw = markerImage.width.toFloat()
            val ih = markerImage.height.toFloat()

            withTransform({
                rotate(
                    degrees = headingDeg.toFloat(),
                    pivot   = Offset(cx, cy)
                )
            }) {
                drawImage(
                    image   = markerImage,
                    topLeft = Offset(cx - iw / 2f, cy - ih / 2f)
                )
            }
        }

        // Coordinate display at bottom
        val coordText = if (latitude != 0.0 || longitude != 0.0)
            "%.6f, %.6f".format(latitude, longitude)
        else
            "Awaiting fix…"

        Text(
            text     = coordText,
            color    = ComposeColor.White,
            fontSize = 11.sp,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 8.dp)
        )

        // Attribution
        Text(
            text     = "⊙ Canvas Map",
            color    = ComposeColor.White.copy(alpha = 0.5f),
            fontSize = 10.sp,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(4.dp)
        )
    }
}

/** Programmatically generated 64×64 blue arrow bitmap for the vehicle marker. */
private fun makeVehicleIconBitmap(): Bitmap {
    val size   = 64
    val bmp    = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bmp)

    val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(230, 0, 120, 255)
        style = Paint.Style.FILL
    }
    val outlinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color       = Color.WHITE
        style       = Paint.Style.STROKE
        strokeWidth = 3f
    }
    val path = Path().apply {
        moveTo(size / 2f, 4f)
        lineTo(size - 8f, size - 4f)
        lineTo(size / 2f, size - 14f)
        lineTo(8f,        size - 4f)
        close()
    }
    canvas.drawPath(path, fillPaint)
    canvas.drawPath(path, outlinePaint)
    return bmp
}
