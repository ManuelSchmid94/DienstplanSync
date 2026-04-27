# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for DienstplanSync (Windows x64).

Expects on the build machine:
  - Tesseract installed via UB-Mannheim installer
    -> C:\\Program Files\\Tesseract-OCR\\
  - Poppler portable extracted to tools\\poppler\\Library\\bin\\
    (downloaded automatically by build_windows.bat)

Run with:
    pyinstaller DienstplanSync_windows.spec --clean
"""

import os
import sys
import glob
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

SPEC_DIR = Path(SPECPATH)

# ── Tesseract (UB-Mannheim default install path) ──────────────────────────────
TESS_DIR = Path(r"C:\Program Files\Tesseract-OCR")
TESS_EXE = TESS_DIR / "tesseract.exe"
TESS_DATA = TESS_DIR / "tessdata"

if not TESS_EXE.exists():
    raise SystemExit(
        "Tesseract nicht gefunden!\n"
        "Bitte installieren: https://github.com/UB-Mannheim/tesseract/wiki\n"
        f"Erwartet in: {TESS_EXE}"
    )

# ── Poppler (portable, extracted by build_windows.bat) ───────────────────────
POPPLER_BIN = SPEC_DIR / "tools" / "poppler" / "Library" / "bin"
if not POPPLER_BIN.exists():
    raise SystemExit(
        "Poppler nicht gefunden!\n"
        f"Erwartet in: {POPPLER_BIN}\n"
        "Bitte build_windows.bat ausfuehren."
    )

# ── Playwright driver ─────────────────────────────────────────────────────────
try:
    import playwright as _pw
    _pw_root        = Path(_pw.__file__).parent
    _pw_driver_node = _pw_root / "driver" / "node.exe"
    _pw_driver_pkg  = _pw_root / "driver" / "package"
except ImportError:
    _pw_driver_node = _pw_driver_pkg = None

# ── Binaries ──────────────────────────────────────────────────────────────────
_binaries = [
    (str(TESS_EXE), "bin"),
    (str(POPPLER_BIN / "pdftoppm.exe"), "bin"),
    (str(POPPLER_BIN / "pdfinfo.exe"),  "bin"),
]

# Collect ALL files from Tesseract-OCR recursively (excluding tessdata and docs).
# A simple glob("*.dll") misses DLLs in subdirectories that the UB-Mannheim
# build may place in nested locations.
import os as _os
for _root, _dirs, _files in _os.walk(str(TESS_DIR)):
    _dirs[:] = [d for d in _dirs if d.lower() not in ("tessdata", "doc", "java", "var", "include")]
    for _fname in _files:
        if _fname.lower() == "tesseract.exe":
            continue  # already added above
        _full = _os.path.join(_root, _fname)
        _rel  = _os.path.relpath(_root, str(TESS_DIR))
        _dest = "bin" if _rel == "." else _os.path.join("bin", _rel)
        _binaries.append((_full, _dest))

# Poppler DLLs
for dll in POPPLER_BIN.glob("*.dll"):
    _binaries.append((str(dll), "bin"))

if _pw_driver_node and _pw_driver_node.exists():
    _binaries.append((str(_pw_driver_node), "playwright/driver"))

# ── Data files ────────────────────────────────────────────────────────────────
_datas = [
    (str(TESS_DATA / "deu.traineddata"), "tessdata"),
]
# Include English tessdata only if present (some installs skip it)
if (TESS_DATA / "eng.traineddata").exists():
    _datas.append((str(TESS_DATA / "eng.traineddata"), "tessdata"))
if _pw_driver_pkg and _pw_driver_pkg.exists():
    _datas.append((str(_pw_driver_pkg), "playwright/driver/package"))

_datas += collect_data_files("playwright", excludes=["driver/node*", "driver/package"])

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(SPEC_DIR / "main.py")],
    pathex=[str(SPEC_DIR)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        "keyring.backends.Windows",
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
    upx=False,
    console=False,      # GUI – kein Konsolenfenster
    argv_emulation=False,
    target_arch=None,   # Nativ-Arch des Build-Systems (x64)
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # .ico-Datei hier eintragen falls vorhanden
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DienstplanSync",
)
