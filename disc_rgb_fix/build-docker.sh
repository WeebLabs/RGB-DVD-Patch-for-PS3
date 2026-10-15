#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
SDK_DIR="${1:-$ROOT_DIR/cell_sdk/cell}"

docker build -t ps3-cellsdk "$ROOT_DIR/docker"
docker run --rm \
    -v "$SDK_DIR":/opt/cell \
    -v "$PROJECT_DIR":/src \
    ps3-cellsdk \
    make -C /src clean all

python3 "$PROJECT_DIR/tools/verify_disc_rgb_fix.py"
