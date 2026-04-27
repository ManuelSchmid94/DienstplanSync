"""
Dienstplan Sync – Entry Point
"""
import sys
import os
import logging
import signal
from pathlib import Path

# ── Frozen-App path setup (PyInstaller) ───────────────────────────────────────
if getattr(sys, "frozen", False):
    _base = Path(sys._MEIPASS)
    _bin = _base / "bin"
    # TESSDATA_PREFIX convention differs by platform:
    #   macOS Homebrew build: points to tessdata/ dir itself
    #   Windows UB-Mannheim build: points to the parent of tessdata/ (Tesseract appends it)
    if sys.platform == "win32":
        os.environ["TESSDATA_PREFIX"] = str(_base)
    else:
        os.environ["TESSDATA_PREFIX"] = str(_base / "tessdata")
    os.environ["PATH"] = str(_bin) + os.pathsep + os.environ.get("PATH", "")
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(_bin))
        except OSError:
            pass
    import pytesseract
    _tess = _bin / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
    if _tess.exists():
        pytesseract.pytesseract.tesseract_cmd = str(_tess)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

# Allow Ctrl+C to quit from terminal
signal.signal(signal.SIGINT, signal.SIG_DFL)

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Also log to file in App Support
try:
    from core import APP_DATA_DIR
    log_file = APP_DATA_DIR / "dienstplan_sync.log"
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)
except Exception:
    pass

logger = logging.getLogger(__name__)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    from core import APP_VERSION
    app.setApplicationName("Dienstplan Sync")
    app.setOrganizationName("OSK")
    app.setApplicationVersion(APP_VERSION)

    icon_path = Path(__file__).parent / "assets" / "icon.icns"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    from core import SETTINGS_FILE
    from storage.settings_manager import SettingsManager
    settings = SettingsManager(SETTINGS_FILE)

    from ui.main_window import MainWindow
    window = MainWindow(settings)
    window.show()

    if settings.auto_sync:
        logger.info("Auto-Sync aktiv – starte in 1 s…")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1000, window._start_sync)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
