# SIH26168 Android Web App

This is a native Android shell for the root SIH26168 Vite/React navigation application.

It loads the current deployed web application inside Android WebView and enables JavaScript, DOM storage, Android location permission bridging, and phone IMU access through the web application's sensor APIs.

## Build without Android Studio

From the repository root:

    cd android_web_app
    chmod +x gradlew
    ./gradlew assembleDebug

APK:

    android_web_app/app/build/outputs/apk/debug/app-debug.apk

Install on a USB-connected Android phone:

    adb install -r app/build/outputs/apk/debug/app-debug.apk

If adb is not installed, install Android SDK Platform Tools and enable USB debugging on the phone.

The wrapper currently loads the same HTTPS deployment URL used by the root web app. If that deployment URL changes, update WEB_APP_URL in app/build.gradle.kts.

This is intentionally a WebView wrapper rather than the older member6_mobile or vizag_nav_app native UI, so the installed APK displays the current root web application's UI.
