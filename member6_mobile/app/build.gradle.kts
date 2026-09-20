plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val ortAndroidRoot = file("${projectDir}/src/main/onnxruntime")
val ortAndroidAar = "com.microsoft.onnxruntime:onnxruntime-android:1.19.2"
val ortAndroidConfig = configurations.detachedConfiguration(project.dependencies.create(ortAndroidAar))

tasks.register("extractOnnxRuntimeAndroid", Copy::class) {
    doFirst {
        delete(ortAndroidRoot)
    }
    from(zipTree(ortAndroidConfig.singleFile)) {
        include("jni/**")
        eachFile {
            val path = relativePath.segments.joinToString("/")
            if (path.startsWith("jni/")) {
                relativePath = RelativePath(true, *("lib" + path.removePrefix("jni")).split("/").filter { it.isNotEmpty() }.toTypedArray())
            }
        }
        includeEmptyDirs = false
    }
    from(zipTree(ortAndroidConfig.singleFile)) {
        include("headers/**")
        eachFile {
            val path = relativePath.segments.joinToString("/")
            if (path.startsWith("headers/")) {
                relativePath = RelativePath(true, *("include/" + path.removePrefix("headers/")).split("/").filter { it.isNotEmpty() }.toTypedArray())
            }
        }
        includeEmptyDirs = false
    }
    into(ortAndroidRoot)
}

android {
    namespace = "org.sih26168.idr"
    compileSdk = 34
    ndkVersion = "26.3.11579264"
    defaultConfig {
        applicationId = "org.sih26168.idr"
        minSdk = 24
        targetSdk = 34
        versionCode = 2
        versionName = "0.2.0"
        ndk {
            abiFilters += "arm64-v8a"
        }
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DANDROID_STL=c++_shared",
                    "-DSIH26168_BUILD_HOST_TOOLS=OFF",
                    "-DIDR_WITH_ONNXRUNTIME=ON",
                    "-DIDR_ONNXRUNTIME_ROOT=${ortAndroidRoot.absolutePath}"
                )
                targets += "idr_jni"
            }
        }
    }
    buildTypes {
        getByName("debug") {
            isDebuggable = true
            buildConfigField("boolean", "ENABLE_ONNX_RUNTIME", "true")
        }
        getByName("release") {
            isMinifyEnabled = false
            buildConfigField("boolean", "ENABLE_ONNX_RUNTIME", "true")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    packaging {
        jniLibs {
            keepDebugSymbols += "**/*.so"
        }
    }
    sourceSets {
        getByName("main") {
            jniLibs.srcDir("src/main/jniLibs")
        }
    }
}

tasks.named("preBuild") {
    dependsOn("extractOnnxRuntimeAndroid")
}

tasks.matching { it.name.startsWith("externalNativeBuild") }.configureEach {
    dependsOn("extractOnnxRuntimeAndroid")
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation(ortAndroidAar)
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
}
