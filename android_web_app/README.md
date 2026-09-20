# SIH26168 Android Web App

Native Android shell for the root SIH26168 Vite/React navigation application.

Build:
    cd android_web_app
    chmod +x gradlew
    ./gradlew assembleDebug

APK:
    app/build/outputs/apk/debug/app-debug.apk

Install:
    adb install -r app/build/outputs/apk/debug/app-debug.apk

The wrapper loads the current HTTPS web deployment and bridges Android location permissions to browser geolocation.
