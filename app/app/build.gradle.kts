plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.compose.compiler)
  alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "com.example.member6app"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.example.member6app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        
        externalNativeBuild {
            cmake {
                cppFlags("-std=c++20")
                arguments("-DIDR_WITH_ONNXRUNTIME=ON", "-DIDR_ONNXRUNTIME_ROOT=C:/Users/anish/Desktop/SIH26168/onnxruntime_extracted")
            }
        }
    }

    sourceSets {
        getByName("main") {
            jniLibs.srcDirs("C:/Users/anish/Desktop/SIH26168/onnxruntime_extracted/lib")
        }
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
      compose = true
      aidl = false
      buildConfig = false
      shaders = false
    }
    
    externalNativeBuild {
        cmake {
            path("src/main/cpp/CMakeLists.txt")
            version = "3.22.1+"
        }
    }

    packaging {
      resources {
        excludes += "/META-INF/{AL2.0,LGPL2.1}"
      }
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
  val composeBom = platform(libs.androidx.compose.bom)
  implementation(composeBom)
  androidTestImplementation(composeBom)

  // Core Android dependencies
  implementation(libs.androidx.core.ktx)
  implementation(libs.androidx.lifecycle.runtime.ktx)
  implementation(libs.androidx.activity.compose)

  // Arch Components
  implementation(libs.androidx.lifecycle.runtime.compose)
  implementation(libs.androidx.lifecycle.viewmodel.compose)

  // Compose
  implementation(libs.androidx.compose.ui)
  implementation(libs.androidx.compose.ui.tooling.preview)
  implementation(libs.androidx.compose.material3)
  implementation("androidx.compose.material:material-icons-extended")
  debugImplementation(libs.androidx.compose.ui.tooling)

  // CameraX
  val camerax_version = "1.3.4"
  implementation("androidx.camera:camera-core:${camerax_version}")
  implementation("androidx.camera:camera-camera2:${camerax_version}")
  implementation("androidx.camera:camera-lifecycle:${camerax_version}")
  implementation("androidx.camera:camera-video:${camerax_version}")
  implementation("androidx.camera:camera-view:${camerax_version}")

  // MapLibre removed — using pure-Compose Canvas map to avoid native crashes

  // Location
  implementation("com.google.android.gms:play-services-location:21.3.0")

  // Permission handling (Accompanist)
  implementation("com.google.accompanist:accompanist-permissions:0.34.0")

  // Coroutines
  implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

  // Tests
  testImplementation(libs.junit)
  testImplementation(libs.kotlinx.coroutines.test)
  androidTestImplementation(libs.androidx.compose.ui.test.junit4)
  debugImplementation(libs.androidx.compose.ui.test.manifest)
}
