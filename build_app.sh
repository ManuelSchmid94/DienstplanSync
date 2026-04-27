#!/usr/bin/env bash
# build_app.sh – Build DienstplanSync.app and package as .dmg
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"
DIST="$SCRIPT_DIR/dist"
APP="$DIST/DienstplanSync.app"
DMG="$DIST/DienstplanSync.dmg"

echo "=== Dienstplan Sync – App Build ==="
echo ""

# ── 1. Clean previous build ───────────────────────────────────────────────────
echo "→ Cleaning previous build..."
rm -rf "$SCRIPT_DIR/build" "$APP" "$DMG"

# ── 2. Build with PyInstaller ─────────────────────────────────────────────────
echo "→ Running PyInstaller (this takes a few minutes)..."
"$VENV/bin/pyinstaller" DienstplanSync.spec --clean --noconfirm

# ── 3. Quick smoke test: check the binary exists ──────────────────────────────
if [ ! -f "$APP/Contents/MacOS/DienstplanSync" ]; then
    echo "ERROR: .app binary not found – build failed."
    exit 1
fi
echo "   .app built successfully: $APP"

# ── 4. Remove macOS quarantine (avoids "damaged app" dialog) ─────────────────
xattr -cr "$APP" 2>/dev/null || true

# ── 5. Package as .dmg ───────────────────────────────────────────────────────
echo "→ Creating .dmg..."
hdiutil create \
    -volname "Dienstplan Sync" \
    -srcfolder "$APP" \
    -ov \
    -format UDZO \
    "$DMG"

echo ""
echo "=== Build complete ==="
echo "  App: $APP"
echo "  DMG: $DMG"
echo ""
echo "Installation:"
echo "  1. Öffne $DMG"
echo "  2. Ziehe DienstplanSync.app in den Programme-Ordner"
echo "  3. Beim ersten Start: Rechtsklick → Öffnen (Gatekeeper-Bypass)"
