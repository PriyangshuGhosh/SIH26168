#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v java >/dev/null 2>&1; then
  echo "Java is required. Install JDK 17 and set JAVA_HOME." >&2
  exit 1
fi

if [ -z "${ANDROID_HOME:-}" ] && [ -z "${ANDROID_SDK_ROOT:-}" ] && [ -d "$HOME/Android/Sdk" ]; then
  export ANDROID_HOME="$HOME/Android/Sdk"
  export ANDROID_SDK_ROOT="$ANDROID_HOME"
fi

if [ ! -f gradle/wrapper/gradle-wrapper.jar ]; then
  if ! command -v gradle >/dev/null 2>&1; then
    echo "Gradle wrapper JAR is not checked into this repository." >&2
    echo "Install system Gradle 8.x, then rerun this script." >&2
    exit 1
  fi
  gradle wrapper --gradle-version 8.7
fi

chmod +x gradlew
./gradlew assembleDebug

echo
echo "APK created at:"
echo "$PWD/app/build/outputs/apk/debug/app-debug.apk"
