#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
PYINSTALLER="${PYINSTALLER:-pyinstaller}"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PROJECT_DIR/.build/pyinstaller-config}"

cd "$PROJECT_DIR"

"$PYINSTALLER" \
  --noconfirm \
  --clean \
  --windowed \
  --name "Codex App かんたん切り替え" \
  --icon "assets/AppIcon.icns" \
  --osx-bundle-identifier "local.study.codex-app-easy-switcher" \
  app.py

/usr/bin/plutil -replace CFBundleShortVersionString -string "0.3.0" \
  "dist/Codex App かんたん切り替え.app/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleVersion -string "3" \
  "dist/Codex App かんたん切り替え.app/Contents/Info.plist"
/usr/bin/plutil -replace LSMinimumSystemVersion -string "12.0" \
  "dist/Codex App かんたん切り替え.app/Contents/Info.plist"

/usr/bin/codesign --force --deep --sign - "dist/Codex App かんたん切り替え.app"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent \
  "dist/Codex App かんたん切り替え.app" \
  "dist/Codex-App-Easy-Switcher-macOS.zip"

MAC_HASH="$(/usr/bin/shasum -a 256 "dist/Codex-App-Easy-Switcher-macOS.zip" | /usr/bin/awk '{print $1}')"
/usr/bin/printf "%s  %s\n" "$MAC_HASH" "Codex-App-Easy-Switcher-macOS.zip" \
  > "dist/SHA256SUMS-macOS.txt"

echo "Built: $PROJECT_DIR/dist/Codex App かんたん切り替え.app"
echo "Archive: $PROJECT_DIR/dist/Codex-App-Easy-Switcher-macOS.zip"
