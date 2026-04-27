# Runtime hook: fix native-binary paths for frozen (PyInstaller) builds.
# Runs before main.py so pytesseract picks up the correct executable path
# even if some other module imports pytesseract during app initialisation.
import sys
import os

if getattr(sys, "frozen", False):
    _base = sys._MEIPASS
    _bin  = os.path.join(_base, "bin")

    # TESSDATA_PREFIX convention differs by platform/build:
    #   macOS Homebrew: points to the tessdata/ dir itself
    #   Windows UB-Mannheim: points to the *parent* of tessdata/ (Tesseract appends "tessdata/")
    if sys.platform == "win32":
        os.environ["TESSDATA_PREFIX"] = _base
    else:
        os.environ["TESSDATA_PREFIX"] = os.path.join(_base, "tessdata")
    os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")

    # Windows: explicitly register bin/ so the OS can find DLLs loaded by
    # tesseract.exe and poppler when spawned as subprocesses.
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(_bin)
        except OSError:
            pass

    # Set pytesseract's executable path early – before any import of core.parser
    # could trigger a pytesseract call with the wrong (default) path.
    try:
        import pytesseract as _pt
        _tess_exe = os.path.join(
            _bin, "tesseract.exe" if sys.platform == "win32" else "tesseract"
        )
        if os.path.isfile(_tess_exe):
            _pt.pytesseract.tesseract_cmd = _tess_exe
    except Exception:
        pass

    # Playwright: bundled headless shell lives in playwright_browsers/.
    # Setting PLAYWRIGHT_BROWSERS_PATH tells Playwright to look there instead of
    # the user's ~/.cache/ms-playwright – so no external browser install is needed.
    _browsers = os.path.join(_base, "playwright_browsers")
    if os.path.isdir(_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers
