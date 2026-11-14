#!/usr/bin/env bash
# Build MePDF macOS Application Bundle (.app) and Disk Image Installer (.dmg)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="1.0.0"
ARCH="${1:-$(uname -m)}"

if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
    PYTHON_BIN="python3"
fi

ARCH_PREFIX=""
if [ "$ARCH" = "x86_64" ] && [ "$(uname -m)" = "arm64" ]; then
    ARCH_PREFIX="arch -x86_64"
fi

echo "==> Using Python: $ARCH_PREFIX $PYTHON_BIN (Target Arch: $ARCH)"

if ! $ARCH_PREFIX "$PYTHON_BIN" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "==> Installing PyInstaller..."
    $ARCH_PREFIX "$PYTHON_BIN" -m pip install pyinstaller
fi

echo "==> Step 1/4: Generating application icons (.icns / .png)..."
$ARCH_PREFIX "$PYTHON_BIN" packaging/generate_icons.py

echo "==> Step 2/4: Building macOS MePDF.app bundle via PyInstaller..."
$ARCH_PREFIX "$PYTHON_BIN" -m PyInstaller --noconfirm --clean MePDF.spec

APP_BUNDLE="$ROOT_DIR/dist/MePDF.app"
if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: Expected $APP_BUNDLE was not created by PyInstaller." >&2
    exit 1
fi

echo "==> Step 3/4: Applying ad-hoc code signature to MePDF.app..."
codesign --force --deep --sign - "$APP_BUNDLE"

echo "==> Step 4/4: Packaging MePDF-$VERSION-macOS-$ARCH.dmg..."
INSTALLERS_DIR="$ROOT_DIR/dist/installers"
DMG_STAGE="$ROOT_DIR/dist/dmg_stage"
DMG_OUT="$INSTALLERS_DIR/MePDF-$VERSION-macOS-$ARCH.dmg"

rm -rf "$DMG_STAGE" "$DMG_OUT"
mkdir -p "$INSTALLERS_DIR" "$DMG_STAGE"

cp -R "$APP_BUNDLE" "$DMG_STAGE/MePDF.app"
ln -s /Applications "$DMG_STAGE/Applications"
cp "$ROOT_DIR/LICENSE" "$DMG_STAGE/LICENSE.txt"

hdiutil create \
    -volname "MePDF $VERSION" \
    -srcfolder "$DMG_STAGE" \
    -ov \
    -format UDZO \
    "$DMG_OUT"

rm -rf "$DMG_STAGE"
echo "==> Done! macOS DMG created at: $DMG_OUT"
