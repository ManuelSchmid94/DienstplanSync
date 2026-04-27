#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_dmg.sh  –  Full build pipeline for DienstplanSync macOS app
#
# Usage:
#   chmod +x build_dmg.sh
#   ./build_dmg.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_NAME="DienstplanSync"
APP_VERSION="1.0.0"
BUNDLE="${APP_NAME}.app"
DMG_NAME="${APP_NAME}-${APP_VERSION}.dmg"
DIST_DIR="dist"
VENV_DIR=".venv"

echo "╔══════════════════════════════════════════════╗"
echo "║  Dienstplan Sync – macOS Build Pipeline      ║"
echo "╚══════════════════════════════════════════════╝"
echo

# ── Helper: generate placeholder icon ────────────────────────────────────────
# MUST be defined before use (bash executes top-to-bottom)
_generate_placeholder_icon() {
    echo "  Generiere Platzhalter-Icon mit Python/Pillow…"
    ICONSET="assets/AppIcon.iconset"
    mkdir -p "$ICONSET"

    python3 - <<'PYEOF'
from PIL import Image, ImageDraw, ImageFont
import pathlib

iconset = pathlib.Path("assets/AppIcon.iconset")
iconset.mkdir(parents=True, exist_ok=True)

SIZES = [16, 32, 64, 128, 256, 512, 1024]

def make(size):
    img = Image.new("RGBA", (size, size), (14, 99, 156, 255))
    d = ImageDraw.Draw(img)
    font_size = max(int(size * 0.52), 8)
    font = None
    for fp in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
               "/System/Library/Fonts/Helvetica.ttc"]:
        try:
            font = ImageFont.truetype(fp, font_size); break
        except Exception:
            pass
    font = font or ImageFont.load_default()
    text = "DS"
    bb = d.textbbox((0, 0), text, font=font)
    x = (size - (bb[2] - bb[0])) / 2 - bb[0]
    y = (size - (bb[3] - bb[1])) / 2 - bb[1]
    d.text((x, y), text, fill="white", font=font)
    return img

for sz in SIZES:
    make(sz).save(iconset / f"icon_{sz}x{sz}.png")
    if sz <= 512:
        make(sz * 2).save(iconset / f"icon_{sz}x{sz}@2x.png")
    print(f"  icon {sz}x{sz} ✓")
PYEOF

    iconutil -c icns "$ICONSET" -o "assets/icon.icns"
    rm -rf "$ICONSET"
    echo "  assets/icon.icns erstellt."
}

# ── 0. Check architecture ─────────────────────────────────────────────────────
ARCH=$(uname -m)
echo "[0/7] Architektur: $ARCH"
if [[ "$ARCH" != "arm64" ]]; then
    echo "  WARNUNG: Kein Apple Silicon erkannt – Build läuft, aber nicht arm64-nativ."
fi

# ── 1. Python venv ─────────────────────────────────────────────────────────────
echo "[1/7] Python Virtual Environment…"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet

# ── 2. Dependencies ────────────────────────────────────────────────────────────
echo "[2/7] Installiere Python-Abhängigkeiten…"
pip install -r requirements.txt --quiet
pip install Pillow --quiet   # needed for icon generation

# ── 3. Playwright Chromium ─────────────────────────────────────────────────────
echo "[3/7] Playwright Chromium Browser installieren…"
playwright install chromium

# ── 4. Icon ────────────────────────────────────────────────────────────────────
echo "[4/7] App-Icon prüfen…"
mkdir -p assets
if [[ ! -f "assets/icon.icns" ]]; then
    echo "  assets/icon.icns fehlt – erstelle Platzhalter…"
    _generate_placeholder_icon   # function is defined above ✓
fi
echo "  Icon OK: assets/icon.icns"

# ── 5. PyInstaller Build ───────────────────────────────────────────────────────
echo "[5/7] PyInstaller Build…"
rm -rf "$DIST_DIR/DienstplanSync" "$DIST_DIR/${BUNDLE}" build/
pyinstaller DienstplanSync.spec --clean --noconfirm

if [[ ! -d "$DIST_DIR/${BUNDLE}" ]]; then
    echo "ERROR: .app Bundle nicht gefunden in $DIST_DIR/"
    exit 1
fi
echo "  .app erstellt: $DIST_DIR/${BUNDLE}"

# ── 6. Playwright Chromium ins Bundle einbetten ───────────────────────────────
echo "[6/7] Playwright Chromium ins App Bundle einbetten…"

# Modern Playwright stores browsers in ~/Library/Caches/ms-playwright on macOS
PW_CACHE="$HOME/Library/Caches/ms-playwright"
BUNDLE_RESOURCES="$DIST_DIR/${BUNDLE}/Contents/Resources"

if [[ -d "$PW_CACHE" ]]; then
    mkdir -p "$BUNDLE_RESOURCES/.local-browsers"
    if ls "$PW_CACHE"/chromium-* &>/dev/null 2>&1; then
        cp -R "$PW_CACHE"/chromium-* "$BUNDLE_RESOURCES/.local-browsers/"
        echo "  Chromium eingebettet ($(du -sh "$BUNDLE_RESOURCES/.local-browsers" | cut -f1))"
    else
        echo "  WARN: Kein Chromium unter $PW_CACHE gefunden."
    fi
else
    echo "  WARN: $PW_CACHE nicht gefunden – Browser muss zur Laufzeit vorhanden sein."
fi

# Wrap the executable so PLAYWRIGHT_BROWSERS_PATH is set at runtime
LAUNCHER="$DIST_DIR/${BUNDLE}/Contents/MacOS/DienstplanSync"
if [[ -f "$LAUNCHER" ]]; then
    mv "$LAUNCHER" "${LAUNCHER}_bin"
    cat > "$LAUNCHER" <<'SHEOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
export PLAYWRIGHT_BROWSERS_PATH="$DIR/../Resources/.local-browsers"
exec "$DIR/DienstplanSync_bin" "$@"
SHEOF
    chmod +x "$LAUNCHER"
    echo "  Launcher-Wrapper erstellt."
fi

# ── 7. DMG Installer ──────────────────────────────────────────────────────────
echo "[7/7] DMG Installer erstellen…"

if ! command -v create-dmg &>/dev/null; then
    if command -v brew &>/dev/null; then
        brew install create-dmg --quiet
    else
        echo "ERROR: create-dmg nicht gefunden und Homebrew nicht verfügbar."
        echo "  Bitte manuell installieren: brew install create-dmg"
        exit 1
    fi
fi

DMG_PATH="$DIST_DIR/$DMG_NAME"
rm -f "$DMG_PATH"

# Try with background image first, fall back to plain layout.
# Both calls include the required positional args: <output.dmg> <source_dir>
if [[ -f "assets/dmg_background.png" ]]; then
    create-dmg \
        --volname "Dienstplan Sync" \
        --volicon "assets/icon.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "${BUNDLE}" 150 185 \
        --hide-extension "${BUNDLE}" \
        --app-drop-link 450 185 \
        --background "assets/dmg_background.png" \
        "$DMG_PATH" \
        "$DIST_DIR/${BUNDLE}"
else
    create-dmg \
        --volname "Dienstplan Sync" \
        --volicon "assets/icon.icns" \
        --window-pos 200 120 \
        --window-size 560 300 \
        --icon-size 100 \
        --icon "${BUNDLE}" 140 150 \
        --hide-extension "${BUNDLE}" \
        --app-drop-link 420 150 \
        "$DMG_PATH" \
        "$DIST_DIR/${BUNDLE}"
fi

echo
echo "╔══════════════════════════════════════════════╗"
echo "║  Build erfolgreich!                          ║"
echo "╚══════════════════════════════════════════════╝"
echo
echo "  .app  →  $DIST_DIR/${BUNDLE}"
echo "  .dmg  →  $DIST_DIR/$DMG_NAME"
echo
echo "Nächste Schritte:"
echo "  1. credentials.json aus Google Cloud Console in"
echo "     ~/Library/Application Support/DienstplanSync/ ablegen"
echo "  2. App starten und Google verbinden"
echo "  3. DMG per E-Mail oder USB-Stick verteilen"
