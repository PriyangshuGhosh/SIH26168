#!/usr/bin/env bash
# Fetch the official ONNX Runtime C++ package into repo .cache/ (gitignored).
# Does not vendor a production speed_estimator.onnx.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VER="${ONNXRUNTIME_VERSION:-1.19.2}"
DEST="${IDR_ONNXRUNTIME_ROOT:-$ROOT/.cache/onnxruntime}"
if [[ -f "$DEST/include/onnxruntime_cxx_api.h" && -e "$DEST/lib/libonnxruntime.so" ]]; then
  echo "already present: $DEST"
  exit 0
fi
mkdir -p "$ROOT/.cache"
TGZ="$ROOT/.cache/onnxruntime-linux-x64-${VER}.tgz"
URL="https://github.com/microsoft/onnxruntime/releases/download/v${VER}/onnxruntime-linux-x64-${VER}.tgz"
echo "downloading $URL"
curl -L --fail -o "$TGZ" "$URL"
rm -rf "$DEST"
mkdir -p "$DEST"
tar -xzf "$TGZ" -C "$ROOT/.cache"
EXTRACT="$ROOT/.cache/onnxruntime-linux-x64-${VER}"
if [[ -d "$EXTRACT" ]]; then
  mv "$EXTRACT/"* "$DEST/"
  rmdir "$EXTRACT"
fi
echo "ONNX Runtime root: $DEST"
