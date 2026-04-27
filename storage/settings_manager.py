"""
Persistent settings backed by JSON.
Sensitive credentials (OSK password) are stored in macOS Keychain via keyring.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import keyring

logger = logging.getLogger(__name__)

_SERVICE_NAME = "DienstplanSync"


class SettingsManager:
    def __init__(self, settings_file: Path) -> None:
        self._path = settings_file
        self._data: dict = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("settings.json unlesbar: %s – starte leer.", e)
                self._data = {}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── Generic key/value ─────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    # ── OSK credentials (Keychain) ─────────────────────────────────────────────

    @property
    def osk_username(self) -> str:
        return self._data.get("osk_username", "")

    @osk_username.setter
    def osk_username(self, value: str) -> None:
        self._data["osk_username"] = value
        self.save()

    @property
    def osk_password(self) -> str:
        username = self.osk_username
        if not username:
            return ""
        try:
            return keyring.get_password(_SERVICE_NAME, username) or ""
        except Exception:
            return ""

    def save_osk_credentials(self, username: str, password: str) -> None:
        """Save username to settings.json and password to macOS Keychain."""
        self._data["osk_username"] = username
        self.save()
        try:
            keyring.set_password(_SERVICE_NAME, username, password)
            logger.info("Passwort im Keychain gespeichert.")
        except Exception as e:
            logger.error("Keychain-Fehler: %s", e)
            raise RuntimeError(f"Passwort konnte nicht sicher gespeichert werden: {e}") from e

    def clear_osk_credentials(self) -> None:
        username = self.osk_username
        if username:
            try:
                keyring.delete_password(_SERVICE_NAME, username)
            except Exception:
                pass
        self._data.pop("osk_username", None)
        self.save()

    # ── PDF output directory ───────────────────────────────────────────────────

    @property
    def pdf_output_dir(self) -> Path:
        raw = self._data.get("pdf_output_dir", "")
        if raw and Path(raw).is_dir():
            return Path(raw)
        return Path.home() / "Downloads"

    @pdf_output_dir.setter
    def pdf_output_dir(self, value: Path) -> None:
        self._data["pdf_output_dir"] = str(value)
        self.save()

    # ── iCal output directory ──────────────────────────────────────────────────

    @property
    def ical_output_dir(self) -> Path:
        raw = self._data.get("ical_output_dir", "")
        if raw and Path(raw).is_dir():
            return Path(raw)
        return Path.home() / "Downloads"

    @ical_output_dir.setter
    def ical_output_dir(self, value: Path) -> None:
        self._data["ical_output_dir"] = str(value)
        self.save()

    @property
    def auto_sync(self) -> bool:
        return bool(self._data.get("auto_sync", False))

    @auto_sync.setter
    def auto_sync(self, value: bool) -> None:
        self._data["auto_sync"] = value
        self.save()
