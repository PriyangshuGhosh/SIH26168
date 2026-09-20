# SIH26168 Android Web App

Native Android shell for the root SIH26168 Vite/React navigation application.

The APK displays the current root web application's UI inside Android WebView instead of the older member6_mobile or Vizag native UI. Android location permission is bridged to browser geolocation, and the HTTPS web app can use the phone's browser sensor APIs.

## Build without Android Studio

From the repository root:

    cd android_web_app
    ./build_apk.sh

The script generates the missing Gradle wrapper JAR with your installed system Gradle 8.x when necessary, then builds the debug APK.

APK:

    app/build/outputs/apk/debug/app-debug.apk

If Gradle reports that the Android SDK cannot be found, set ANDROID_HOME to your SDK directory before running the script.

## Install on a phone

Enable Developer Options and USB debugging on the Android phone, connect it by USB, then:

    adb install -r app/build/outputs/apk/debug/app-debug.apk

If adb is not installed, install Android SDK Platform Tools.

## Deployment URL

The wrapper loads the HTTPS deployment URL currently used by the root web app. If that deployment URL changes, update WEB_APP_URL in app/build.gradle.kts.

This wrapper does not make the web app offline: the installed APK needs network access to load the deployed web application and its ML API.
