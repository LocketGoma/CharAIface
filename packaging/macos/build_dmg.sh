#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_PATH="$PROJECT_ROOT/dist/macos/CharAIface.app"
DIST_PATH="$PROJECT_ROOT/dist/macos"
DMG_PATH="$DIST_PATH/CharAIface-macos.dmg"
STAGING_DIR="$PROJECT_ROOT/build/macos-dmg-staging"

if [[ ! -d "$APP_PATH" ]]; then
  echo "[ERROR] App bundle was not found: $APP_PATH"
  echo "Build it first with: ./packaging/macos/build_macos.sh"
  exit 1
fi

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$APP_PATH" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

rm -f "$DMG_PATH"
hdiutil create \
  -volname "CharAIface" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "[CharAIface] macOS DMG built: $DMG_PATH"
