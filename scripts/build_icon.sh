#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
SOURCE="${1:-$PROJECT_DIR/assets/app_icon_source.png}"
ICONSET="$PROJECT_DIR/.build/AppIcon.iconset"
OUTPUT="$PROJECT_DIR/assets/AppIcon.icns"

mkdir -p "$ICONSET"

for SIZE in 16 32 128 256 512; do
  /usr/bin/sips -z "$SIZE" "$SIZE" "$SOURCE" \
    --out "$ICONSET/icon_${SIZE}x${SIZE}.png" >/dev/null
  DOUBLE=$((SIZE * 2))
  /usr/bin/sips -z "$DOUBLE" "$DOUBLE" "$SOURCE" \
    --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png" >/dev/null
done

/usr/bin/iconutil -c icns "$ICONSET" -o "$OUTPUT"
echo "Built: $OUTPUT"
