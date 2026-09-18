package com.example.member6app

import android.content.Context
import java.io.File
import java.io.FileOutputStream

object AssetProvisioner {
    fun copyAssetTree(context: Context, assetDir: String, destDir: File) {
        destDir.mkdirs()
        val names = context.assets.list(assetDir) ?: return
        for (name in names) {
            val child = "$assetDir/$name"
            val kids = context.assets.list(child)
            if (kids != null && kids.isNotEmpty()) {
                copyAssetTree(context, child, File(destDir, name))
            } else {
                context.assets.open(child).use { input ->
                    FileOutputStream(File(destDir, name)).use { output ->
                        input.copyTo(output)
                    }
                }
            }
        }
    }
}
