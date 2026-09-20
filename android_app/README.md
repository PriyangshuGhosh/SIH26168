# SIH26168 Android application

This directory is the native Android shell for the **current root React/Vite application**. It is not the older vizag_nav_app and it is not the older member6_mobile UI.

The Android app packages the current web UI into a local Android WebView, so the same navigation HUD, diagnostics, map, simulation controls, sensor pipeline, and engine logic are used on the phone.

## Local build (no Android Studio)

From the repository root:

~~~bash
npm install
npm run lint
npm run build:web

# Requires JDK 17, Gradle 8.7+, and Android SDK platform 35/build-tools 35.0.0.
gradle -p android_app assembleDebug
~~~

APK:

~~~text
android_app/app/build/outputs/apk/debug/app-debug.apk
~~~

Install over USB:

~~~bash
adb install -r android_app/app/build/outputs/apk/debug/app-debug.apk
~~~

Enable **Developer options → USB debugging** on the phone first.

## What is packaged

- Current root src/ React application.
- Leaflet map and current navigation HUD.
- Phone accelerometer/gyroscope/orientation through Android WebView device APIs.
- High-accuracy Android geolocation with runtime location permission.
- Member 1/2/3/4/5 TypeScript engine path already used by the web application.
- Synthetic-drive mode for deterministic demonstrations.

## ML note

The current web MlSpeedService calls /api/ml/predict when a server is available and has an explicit edge fallback when it is not. The standalone APK has no Node/Express server, so the APK's dead-reckoning path uses that existing fallback unless a future on-device ONNX adapter is added. This build therefore must not be described as hardware-validated real-ML navigation.

## GitHub Actions

Every push to main also runs .github/workflows/android-apk.yml. It builds the web app, builds this Android project, and publishes app-debug.apk as a workflow artifact.
