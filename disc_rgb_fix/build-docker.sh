#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
SDK_DIR="${1:-$ROOT_DIR/cell_sdk/cell}"

# vshtask import stub from webMAN MOD (not part of the Cell SDK).
STUB="$PROJECT_DIR/lib/libvshtask_export_stub.a"
STUB_URL="https://raw.githubusercontent.com/aldostools/webMAN-MOD/5c1b73b831d15d1d4be97d480a24b35a08f0c025/lib/libvshtask_export_stub.a"
STUB_SHA256="f53326ecaef8247fce462fc36b88fe589cdd62051b4aa033789a836c27107807"
if [ ! -f "$STUB" ]; then
    mkdir -p "$PROJECT_DIR/lib"
    curl -sfL -o "$STUB" "$STUB_URL"
fi
if [ "$(shasum -a 256 "$STUB" | cut -d' ' -f1)" != "$STUB_SHA256" ]; then
    echo "lib/libvshtask_export_stub.a does not match webMAN MOD's file" >&2
    exit 1
fi

docker build -t ps3-cellsdk "$ROOT_DIR/docker"
docker run --rm \
    -v "$SDK_DIR":/opt/cell \
    -v "$PROJECT_DIR":/src \
    ps3-cellsdk \
    make -C /src clean all

python3 "$PROJECT_DIR/tools/verify_disc_rgb_fix.py"
