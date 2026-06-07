#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
PYINSTALLER="${PYINSTALLER:-pyinstaller}"

cd "$PROJECT_DIR"

"$PYINSTALLER" \
  --noconfirm \
  --clean \
  --windowed \
  --name "Codex App かんたん切り替え" \
  --icon "assets/AppIcon.icns" \
  --osx-bundle-identifier "local.study.codex-app-easy-switcher" \
  app.py

/usr/bin/plutil -replace CFBundleShortVersionString -string "0.1.0" \
  "dist/Codex App かんたん切り替え.app/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleVersion -string "1" \
  "dist/Codex App かんたん切り替え.app/Contents/Info.plist"
/usr/bin/plutil -replace LSMinimumSystemVersion -string "12.0" \
  "dist/Codex App かんたん切り替え.app/Contents/Info.plist"

/usr/bin/codesign --force --deep --sign - "dist/Codex App かんたん切り替え.app"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent \
  "dist/Codex App かんたん切り替え.app" \
  "dist/Codex-App-Easy-Switcher-macOS.zip"

echo "Built: $PROJECT_DIR/dist/Codex App かんたん切り替え.app"
echo "Archive: $PROJECT_DIR/dist/Codex-App-Easy-Switcher-macOS.zip"
