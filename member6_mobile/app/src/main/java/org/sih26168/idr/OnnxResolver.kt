package org.sih26168.idr

import java.io.File

object OnnxResolver {
    fun resolve(filesDir: File): String {
        if (!BuildConfig.ENABLE_ONNX_RUNTIME) {
            return "mock"
        }

        val candidate = File(filesDir, "speed_estimator.onnx")
        if (!candidate.exists() || candidate.length() <= 16L) {
            return "mock"
        }

        val text = runCatching { candidate.readText() }.getOrNull()
        if (text != null && text.trim().startsWith("mock", ignoreCase = true)) {
            return "mock"
        }

        val maybeValid = runCatching {
            candidate.inputStream().buffered().use { stream ->
                val header = ByteArray(8)
                val read = stream.read(header)
                if (read < 8) false else true
            }
        }.getOrElse { false }

        return if (maybeValid) candidate.absolutePath else "mock"
    }
}
