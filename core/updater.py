"""
Auto-updater for DienstplanSync (macOS).

Update server must serve a JSON file at UPDATE_URL with this shape:
  {"version": "1.2.0", "url": "https://example.com/DienstplanSync.dmg"}

The update flow:
  1. Background thread fetches the JSON and compares versions.
  2. If a newer version exists, a signal notifies the main window.
  3. On user confirmation: download DMG → mount → copy new .app to temp dir →
     unmount → spawn a shell script that replaces the old .app after we quit →
     call app.quit().
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)


def check_for_update(update_url: str, current_version: str) -> Optional[Tuple[str, str]]:
    """
    Fetch update_url and return (new_version, dmg_url) if a newer version exists.
    Returns None on error or if already up-to-date.
    """
    if not update_url:
        return None
    try:
        import urllib.request
        req = urllib.request.Request(update_url, headers={"User-Agent": "DienstplanSync"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        new_ver = data.get("version", "").strip()
        dmg_url = data.get("url", "").strip()
        if new_ver and dmg_url and _newer(new_ver, current_version):
            return new_ver, dmg_url
    except Exception as exc:
        logger.debug("Update-Prüfung fehlgeschlagen: %s", exc)
    return None


def download_and_install(
    dmg_url: str,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> bool:
    """
    Download *dmg_url*, mount the image, copy the new .app next to the running one,
    spawn a shell script that replaces the old app after we exit, then return True.
    The caller must call app.quit() after this returns True.
    """
    def _log(msg: str) -> None:
        logger.info(msg)
        if log_cb:
            log_cb(msg)

    if sys.platform != "darwin":
        _log("Auto-Update ist nur unter macOS verfügbar.")
        return False

    if not getattr(sys, "frozen", False):
        _log("Auto-Update funktioniert nur in der fertigen .app-Version.")
        return False

    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="dplan_update_"))

        # ── 1. Download DMG ────────────────────────────────────────────────────
        _log("Update wird heruntergeladen…")
        dmg_path = tmp_dir / "DienstplanSync_update.dmg"

        import urllib.request

        def _progress(count: int, block: int, total: int) -> None:
            if progress_cb and total > 0:
                progress_cb(min(100, int(count * block * 100 / total)))

        urllib.request.urlretrieve(str(dmg_url), str(dmg_path), _progress)
        _log("Download abgeschlossen.")

        # ── 2. Mount DMG ───────────────────────────────────────────────────────
        _log("DMG wird eingehängt…")
        mount_point = tmp_dir / "mount"
        mount_point.mkdir()
        subprocess.run(
            [
                "hdiutil", "attach", str(dmg_path),
                "-mountpoint", str(mount_point),
                "-nobrowse", "-quiet",
            ],
            check=True,
            timeout=60,
        )

        # ── 3. Find the .app inside the DMG ───────────────────────────────────
        app_in_dmg: Optional[Path] = None
        for item in mount_point.iterdir():
            if item.suffix == ".app":
                app_in_dmg = item
                break
        if app_in_dmg is None:
            raise FileNotFoundError("Keine .app-Datei im DMG gefunden.")

        # ── 4. Copy new app to a staging area ─────────────────────────────────
        _log(f"Neue Version: {app_in_dmg.name}")
        staged_app = tmp_dir / "DienstplanSync_new.app"
        subprocess.run(["ditto", str(app_in_dmg), str(staged_app)], check=True, timeout=120)

        # ── 5. Detach DMG ──────────────────────────────────────────────────────
        subprocess.run(["hdiutil", "detach", str(mount_point), "-quiet"], check=False, timeout=30)

        # ── 6. Determine path of the currently running .app ───────────────────
        # sys.executable → …/DienstplanSync.app/Contents/MacOS/DienstplanSync
        current_app = Path(sys.executable).parent.parent.parent
        if current_app.suffix != ".app":
            raise RuntimeError(f"Konnte .app-Pfad nicht bestimmen: {current_app}")

        # ── 7. Write a shell script that replaces the app after we quit ────────
        install_script = tmp_dir / "install_update.sh"
        install_script.write_text(
            f"""#!/bin/bash
sleep 2
if ditto "{staged_app}" "{current_app}" 2>/dev/null; then
    open "{current_app}"
else
    # Needs admin privileges (app is in /Applications)
    osascript -e 'do shell script "ditto \\"{staged_app}\\" \\"{current_app}\\"" with administrator privileges' && open "{current_app}"
fi
rm -rf "{tmp_dir}" 2>/dev/null
"""
        )
        install_script.chmod(0o755)

        _log("Installer-Script wird gestartet…")
        subprocess.Popen(
            ["bash", str(install_script)],
            close_fds=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        _log("Update bereit – App wird neu gestartet.")
        return True

    except Exception as exc:
        logger.exception("Update fehlgeschlagen")
        if log_cb:
            log_cb(f"Update fehlgeschlagen: {exc}")
        return False


def _newer(a: str, b: str) -> bool:
    def _parse(v: str) -> tuple:
        return tuple(int(x) for x in v.split(".") if x.isdigit())
    try:
        return _parse(a) > _parse(b)
    except Exception:
        return False
