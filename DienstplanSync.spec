# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for DienstplanSync.app (macOS arm64 / Apple Silicon).

What gets bundled:
  - All Python dependencies (PySide6, playwright, pytesseract, pdf2image, keyring, …)
  - Tesseract binary + dylib chain + German/English tessdata
  - Poppler binaries (pdftoppm, pdfinfo) + dylib chain
  - Playwright Node.js driver (node binary + JS package)

What is NOT bundled:
  - Playwright browser (Chromium) – read from ~/.cache/ms-playwright/
    Run `playwright install chromium` once on any new machine.
"""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

BREW   = "/opt/homebrew"
SPEC_DIR = Path(SPECPATH)

# ── Playwright driver ─────────────────────────────────────────────────────────
try:
    import playwright as _pw
    _pw_root          = Path(_pw.__file__).parent
    _pw_driver_node   = _pw_root / "driver" / "node"
    _pw_driver_pkg    = _pw_root / "driver" / "package"
except ImportError:
    _pw_root = _pw_driver_node = _pw_driver_pkg = None

_binaries = [
    # Native binaries – PyInstaller auto-collects their dylib chains
    (f"{BREW}/bin/tesseract", "bin"),
    (f"{BREW}/bin/pdftoppm",  "bin"),
    (f"{BREW}/bin/pdfinfo",   "bin"),
]
if _pw_driver_node and _pw_driver_node.exists():
    _binaries.append((str(_pw_driver_node), "playwright/driver"))

_datas = [
    (f"{BREW}/share/tessdata/deu.traineddata", "tessdata"),
]
if Path(f"{BREW}/share/tessdata/eng.traineddata").exists():
    _datas.append((f"{BREW}/share/tessdata/eng.traineddata", "tessdata"))

if _pw_driver_pkg and _pw_driver_pkg.exists():
    _datas.append((str(_pw_driver_pkg), "playwright/driver/package"))

# ── Bundle Playwright headless shell (so users need no extra installation) ───
# We use headless=True, so only the headless shell is needed (187 MB vs 330 MB).
_ms_playwright = Path.home() / "Library" / "Caches" / "ms-playwright"
_hs_dirs = sorted(_ms_playwright.glob("chromium_headless_shell-*"))
if not _hs_dirs:
    raise SystemExit(
        "Playwright headless shell nicht gefunden!\n"
        "Bitte ausfuehren: playwright install chromium\n"
    )
_hs_dir = _hs_dirs[-1]  # newest revision
_datas.append((str(_hs_dir), f"playwright_browsers/{_hs_dir.name}"))

# Remaining playwright data (json manifests, license files …)
_datas += collect_data_files("playwright", excludes=["driver/node", "driver/package"])

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(SPEC_DIR / "main.py")],
    pathex=[str(SPEC_DIR)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        "keyring.backends.macOS",
        "keyring.backends.fail",
        "playwright.sync_api",
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "PySide6.QtNetwork",
    ],
    hookspath=["hooks"],
    runtime_hooks=["runtime_hooks/rthook_paths.py"],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pdfplumber",
              "google", "google_auth_oauthlib", "googleapiclient"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DienstplanSync",
    debug=False,
    strip=False,
    upx=False,           # UPX corrupts arm64 + Qt binaries
    console=False,       # GUI app – no terminal window
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DienstplanSync",
)

app = BUNDLE(
    coll,
    name="DienstplanSync.app",
    icon=None,
    bundle_identifier="de.osk.dienstplansync",
    version="1.0.0",
    info_plist={
        "CFBundleName":               "Dienstplan Sync",
        "CFBundleDisplayName":        "Dienstplan Sync",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion":            "1.0.0",
        "NSHighResolutionCapable":    True,
        "NSRequiresAquaSystemAppearance": False,
        "LSMinimumSystemVersion":     "13.0",
        "NSAppTransportSecurity":     {"NSAllowsArbitraryLoads": True},
        # Required for Playwright / headless Chromium:
        "com.apple.security.cs.allow-jit":                    True,
        "com.apple.security.cs.disable-library-validation":   True,
    },
)
