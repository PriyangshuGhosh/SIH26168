#!/usr/bin/env bash
# Cross-compile libidr_engine.so for Android arm64-v8a.
# Device runtime / performance is NOT VALIDATED by this script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NDK="${ANDROID_NDK:-${ANDROID_NDK_HOME:-}}"
if [[ -z "$NDK" ]]; then
  for c in \
    "$HOME/Android/Sdk/ndk" \
    "$HOME/Library/Android/sdk/ndk" \
    /opt/android-ndk \
    /usr/local/lib/android/sdk/ndk
  do
    if [[ -d "$c" ]]; then
      NDK="$(ls -d "$c"/* 2>/dev/null | tail -n 1 || true)"
      break
    fi
  done
fi
if [[ -z "$NDK" || ! -f "$NDK/build/cmake/android.toolchain.cmake" ]]; then
  echo "ANDROID NDK not found. Set ANDROID_NDK to the NDK root." >&2
  echo "ANDROID PERFORMANCE: NOT VALIDATED" >&2
  exit 2
fi
BUILD="$ROOT/build-android"
cmake -S "$ROOT" -B "$BUILD" \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-24 \
  -DANDROID_STL=c++_shared \
  -DCMAKE_BUILD_TYPE=Release \
  -DSIH26168_BUILD_MEMBER5=ON \
  -DIDR_WITH_ONNXRUNTIME=OFF
cmake --build "$BUILD" --target idr_engine -j
echo "built: $BUILD/member5_engine/libidr_engine.so"
echo "ANDROID PERFORMANCE: NOT VALIDATED"
