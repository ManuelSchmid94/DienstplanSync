"""
Shared paths and app-wide constants.
"""
import sys
from pathlib import Path

APP_VERSION = "1.1.0"

# URL that returns a JSON object: {"version": "X.Y.Z", "url": "https://…/DienstplanSync.dmg"}
# Leave empty to disable update checks.
UPDATE_URL = "https://api.github.com/repos/ManuelSchmid94/DienstplanSync/releases/latest"

if sys.platform == "win32":
    import os as _os
    _roaming = _os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    APP_DATA_DIR = Path(_roaming) / "DienstplanSync"
elif sys.platform == "darwin":
    APP_DATA_DIR = Path.home() / "Library" / "Application Support" / "DienstplanSync"
else:
    APP_DATA_DIR = Path.home() / ".config" / "DienstplanSync"

APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

CREDENTIALS_FILE = APP_DATA_DIR / "credentials.json"
TOKEN_FILE = APP_DATA_DIR / "token.json"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"
PDF_CACHE = APP_DATA_DIR / "cache.pdf"
