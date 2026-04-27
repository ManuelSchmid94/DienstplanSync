"""
Main application window for Dienstplan Sync.
All long-running work (Playwright, PDF parsing) runs in QThread workers
to keep the UI responsive.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
    QCheckBox, QGroupBox, QMessageBox, QFileDialog, QFrame,
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal, Slot, QThread, QObject, QTimer
from PySide6.QtGui import QFont

from ui.log_widget import LogWidget
from ui.shift_review_dialog import ShiftReviewDialog
from storage.settings_manager import SettingsManager
from core import APP_DATA_DIR, PDF_CACHE, APP_VERSION, UPDATE_URL

logger = logging.getLogger(__name__)


# ── Worker thread ──────────────────────────────────────────────────────────────

class SyncWorker(QObject):
    log = Signal(str, str)   # message, level
    finished = Signal(object) # list[Shift] – emitted after successful parsing
    error = Signal(str)

    def __init__(
        self,
        username: str,
        password: str,
        pdf_path: Path,
        pdf_output_dir: Path,
    ):
        super().__init__()
        self._username = username
        self._password = password
        self._pdf_path = pdf_path
        self._pdf_output_dir = pdf_output_dir

    def run(self):
        from datetime import datetime

        def _log(msg: str, level: str = "INFO"):
            self.log.emit(msg, level)

        try:
            # Step 1 – download PDF
            _log("── Schritt 1/2: PDF herunterladen ──────────────────")
            from core.osk_client import download_pdf
            download_pdf(
                username=self._username,
                password=self._password,
                output_path=self._pdf_path,
                log=_log,
            )

            # Copy PDF to user-chosen output directory
            next_month = _next_month_label()
            pdf_dest = self._pdf_output_dir / f"Dienstplan_{next_month}.pdf"
            import shutil
            shutil.copy2(self._pdf_path, pdf_dest)
            _log(f"PDF gespeichert: {pdf_dest}", "OK")

            # Step 2 – parse PDF
            _log("── Schritt 2/2: PDF parsen ──────────────────────────")
            from core.parser import parse_pdf
            year_hint = datetime.now().year
            if datetime.now().month == 12:
                year_hint += 1
            shifts = parse_pdf(self._pdf_path, year_hint=year_hint)
            if not shifts:
                _log("Keine Schichten im PDF gefunden.", "WARN")
                self.finished.emit([])
                return
            _log(f"{len(shifts)} Schicht(en) erkannt – Bitte in der Vorschau prüfen.", "OK")

            self.finished.emit(shifts)

        except Exception as e:
            logger.exception("Sync-Fehler")
            self.error.emit(str(e))


def _next_month_label() -> str:
    from datetime import datetime
    now = datetime.now()
    if now.month == 12:
        return f"{now.year + 1}-01"
    return f"{now.year}-{now.month + 1:02d}"


# ── Update checker worker ──────────────────────────────────────────────────────

class UpdateWorker(QObject):
    update_available = Signal(str, str)  # (new_version, dmg_url)

    def run(self) -> None:
        from core.updater import check_for_update
        result = check_for_update(UPDATE_URL, APP_VERSION)
        if result:
            self.update_available.emit(*result)


class InstallWorker(QObject):
    log     = Signal(str)
    progress = Signal(int)
    done    = Signal(bool)

    def __init__(self, dmg_url: str):
        super().__init__()
        self._url = dmg_url

    def run(self) -> None:
        from core.updater import download_and_install
        ok = download_and_install(
            self._url,
            log_cb=lambda m: self.log.emit(m),
            progress_cb=lambda p: self.progress.emit(p),
        )
        self.done.emit(ok)


# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self._settings = settings
        self._thread: QThread | None = None
        self._worker: SyncWorker | None = None
        self._update_thread: QThread | None = None
        self._install_thread: QThread | None = None
        self._pending_dmg_url: str = ""

        self.setWindowTitle("Dienstplan Sync")
        self.setMinimumSize(560, 560)
        self._build_ui()
        self._restore_settings()

        # Kick off update check 8 s after start so it doesn't block the UI
        if UPDATE_URL:
            QTimer.singleShot(8000, self._check_for_update)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(self._build_header())
        self._update_banner = self._build_update_banner()
        layout.addWidget(self._update_banner)
        layout.addWidget(self._build_osk_group())
        layout.addWidget(self._build_log_group())
        layout.addWidget(self._build_sync_row())

        self._apply_stylesheet()

    def _build_update_banner(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("updateBanner")
        frame.setVisible(False)
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 6, 12, 6)

        self._update_label = QLabel()
        self._update_label.setObjectName("updateLabel")
        row.addWidget(self._update_label, stretch=1)

        self._update_progress = QProgressBar()
        self._update_progress.setFixedWidth(120)
        self._update_progress.setRange(0, 100)
        self._update_progress.setVisible(False)
        row.addWidget(self._update_progress)

        self._install_btn = QPushButton("Jetzt aktualisieren")
        self._install_btn.setObjectName("primaryBtn")
        self._install_btn.setFixedWidth(170)
        self._install_btn.clicked.connect(self._start_install)
        row.addWidget(self._install_btn)

        dismiss_btn = QPushButton("✕")
        dismiss_btn.setObjectName("secondaryBtn")
        dismiss_btn.setFixedSize(28, 28)
        dismiss_btn.clicked.connect(lambda: frame.setVisible(False))
        row.addWidget(dismiss_btn)

        return frame

    def _build_header(self) -> QLabel:
        label = QLabel("Dienstplan Sync")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        label.setFont(font)
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("header")
        return label

    def _build_osk_group(self) -> QGroupBox:
        box = QGroupBox("OSK Dienstplan Timeoffice Zugangsdaten")
        layout = QVBoxLayout(box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Benutzername:"))
        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("z. B. m.mustermann")
        row1.addWidget(self._username_edit)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Passwort:      "))
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.Password)
        self._password_edit.setPlaceholderText("Passwort")
        row2.addWidget(self._password_edit)
        layout.addLayout(row2)

        self._save_creds_btn = QPushButton("Zugangsdaten speichern")
        self._save_creds_btn.setObjectName("secondaryBtn")
        self._save_creds_btn.clicked.connect(self._save_credentials)
        layout.addWidget(self._save_creds_btn, alignment=Qt.AlignRight)

        # PDF output directory
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("PDF-Ordner:    "))
        self._pdf_dir_label = QLabel()
        self._pdf_dir_label.setObjectName("pathLabel")
        self._pdf_dir_label.setWordWrap(False)
        row3.addWidget(self._pdf_dir_label, stretch=1)
        self._pdf_dir_btn = QPushButton("Ordner wählen…")
        self._pdf_dir_btn.setObjectName("secondaryBtn")
        self._pdf_dir_btn.clicked.connect(self._choose_pdf_dir)
        row3.addWidget(self._pdf_dir_btn)
        layout.addLayout(row3)

        # iCal output directory
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("iCal-Ordner:   "))
        self._ical_dir_label = QLabel()
        self._ical_dir_label.setObjectName("pathLabel")
        self._ical_dir_label.setWordWrap(False)
        row4.addWidget(self._ical_dir_label, stretch=1)
        self._ical_dir_btn = QPushButton("Ordner wählen…")
        self._ical_dir_btn.setObjectName("secondaryBtn")
        self._ical_dir_btn.clicked.connect(self._choose_ical_dir)
        row4.addWidget(self._ical_dir_btn)
        layout.addLayout(row4)

        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("Status")
        layout = QVBoxLayout(box)
        self._log = LogWidget()
        self._log.setMinimumHeight(260)
        layout.addWidget(self._log)

        clear_btn = QPushButton("Log leeren")
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.setFixedWidth(100)
        clear_btn.clicked.connect(self._log.clear_log)
        layout.addWidget(clear_btn, alignment=Qt.AlignRight)
        return box

    def _build_sync_row(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)

        self._auto_sync_cb = QCheckBox("Auto-Sync täglich")
        self._auto_sync_cb.toggled.connect(self._on_auto_sync_toggled)
        row.addWidget(self._auto_sync_cb)

        row.addStretch()

        self._sync_btn = QPushButton("  Jetzt synchronisieren  ")
        self._sync_btn.setObjectName("primaryBtn")
        self._sync_btn.clicked.connect(self._start_sync)
        row.addWidget(self._sync_btn)

        return container

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #252526;
                color: #cccccc;
            }
            QGroupBox {
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                margin-top: 8px;
                font-weight: bold;
                color: #9cdcfe;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                color: #cccccc;
            }
            QLabel#header {
                color: #4fc1ff;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                color: #d4d4d4;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 14px;
                color: #cccccc;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #777;
            }
            QPushButton#primaryBtn {
                background-color: #0e639c;
                border-color: #1177bb;
                color: white;
                font-weight: bold;
            }
            QPushButton#primaryBtn:hover {
                background-color: #1177bb;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #2d4a5c;
                color: #888;
                border-color: #3a5a6c;
            }
            QPushButton#secondaryBtn {
                background-color: transparent;
                border-color: #555;
                color: #9cdcfe;
                font-size: 11px;
                padding: 3px 10px;
            }
            QCheckBox {
                color: #cccccc;
            }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border: 1px solid #555;
                border-radius: 3px;
                background: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background: #007acc;
                border-color: #007acc;
            }
            QLabel#pathLabel {
                color: #858585;
                font-size: 11px;
                font-family: Menlo, monospace;
            }
            QFrame#updateBanner {
                background-color: #0d3a5c;
                border: 1px solid #1177bb;
                border-radius: 6px;
            }
            QLabel#updateLabel {
                color: #9cdcfe;
                font-weight: bold;
            }
            QProgressBar {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 3px;
                text-align: center;
                color: #cccccc;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 3px;
            }
        """)

    # ── Settings restore ───────────────────────────────────────────────────────

    def _restore_settings(self) -> None:
        self._username_edit.setText(self._settings.osk_username)
        self._password_edit.setText(self._settings.osk_password)
        self._auto_sync_cb.setChecked(self._settings.auto_sync)
        self._pdf_dir_label.setText(str(self._settings.pdf_output_dir))
        self._ical_dir_label.setText(str(self._settings.ical_output_dir))

    # ── Slots ──────────────────────────────────────────────────────────────────

    @Slot()
    def _choose_pdf_dir(self) -> None:
        current = str(self._settings.pdf_output_dir)
        chosen = QFileDialog.getExistingDirectory(
            self, "PDF-Zielordner wählen", current,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if chosen:
            self._settings.pdf_output_dir = Path(chosen)
            self._pdf_dir_label.setText(chosen)
            self._log.append_line(f"PDF-Ordner gesetzt: {chosen}", "OK")

    @Slot()
    def _choose_ical_dir(self) -> None:
        current = str(self._settings.ical_output_dir)
        chosen = QFileDialog.getExistingDirectory(
            self, "iCal-Zielordner wählen", current,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if chosen:
            self._settings.ical_output_dir = Path(chosen)
            self._ical_dir_label.setText(chosen)
            self._log.append_line(f"iCal-Ordner gesetzt: {chosen}", "OK")

    @Slot()
    def _save_credentials(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        if not username or not password:
            QMessageBox.warning(self, "Fehler", "Benutzername und Passwort dürfen nicht leer sein.")
            return
        try:
            self._settings.save_osk_credentials(username, password)
            self._log.append_line("Zugangsdaten sicher im macOS Keychain gespeichert.", "OK")
        except RuntimeError as e:
            self._log.append_line(f"Fehler beim Speichern: {e}", "ERROR")

    @Slot(bool)
    def _on_auto_sync_toggled(self, checked: bool) -> None:
        self._settings.auto_sync = checked
        if checked:
            self._log.append_line("Auto-Sync aktiviert (täglich beim App-Start).", "INFO")

    @Slot()
    def _start_sync(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        if not username or not password:
            QMessageBox.warning(self, "Fehler", "Bitte Benutzername und Passwort eingeben.")
            return

        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Synchronisiere…")
        self._log.append_line("=" * 50)
        self._log.append_line("Sync gestartet…")

        self._worker = SyncWorker(
            username, password, PDF_CACHE,
            self._settings.pdf_output_dir,
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._on_sync_log)
        self._worker.finished.connect(self._on_parse_done)
        self._worker.error.connect(self._on_sync_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._reset_sync_btn)
        self._thread.start()

    @Slot()
    def _reset_sync_btn(self) -> None:
        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("  Jetzt synchronisieren  ")

    @Slot(str, str)
    def _on_sync_log(self, msg: str, level: str) -> None:
        self._log.append_line(msg, level)

    @Slot(object)
    def _on_parse_done(self, shifts: list) -> None:
        if not shifts:
            self._log.append_line("Keine Schichten gefunden – kein Kalender erstellt.", "WARN")
            return

        dlg = ShiftReviewDialog(shifts, parent=self)
        if dlg.exec() != ShiftReviewDialog.Accepted:
            self._log.append_line("Vorschau abgebrochen – keine iCal-Datei erstellt.", "INFO")
            return

        selected = dlg.get_selected_shifts()
        if not selected:
            self._log.append_line("Keine Schichten ausgewählt – keine iCal-Datei erstellt.", "WARN")
            return

        self._log.append_line("── Schritt 3/3: iCal-Datei erstellen ───────────────")
        from core.ical_export import generate_ical
        next_month = _next_month_label()
        ics_path = self._settings.ical_output_dir / f"Dienstplan_{next_month}.ics"
        generate_ical(selected, ics_path, log=lambda m, l="INFO": self._log.append_line(m, l))
        self._log.append_line(f"Fertig! {len(selected)} Schicht(en) → {ics_path}", "OK")
        if sys.platform == "win32":
            os.startfile(str(ics_path))
        else:
            subprocess.Popen(["open", str(ics_path)])
        self._log.append_line("iCal-Datei wird geöffnet…", "INFO")

    @Slot(str)
    def _on_sync_error(self, msg: str) -> None:
        self._log.append_line(f"FEHLER: {msg}", "ERROR")
        QMessageBox.critical(self, "Sync-Fehler", msg)

    # ── Update check & install ─────────────────────────────────────────────────

    @Slot()
    def _check_for_update(self) -> None:
        worker = UpdateWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.update_available.connect(self._on_update_available)
        worker.update_available.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        self._update_thread = thread
        thread.start()

    @Slot(str, str)
    def _on_update_available(self, version: str, dmg_url: str) -> None:
        self._pending_dmg_url = dmg_url
        self._update_label.setText(
            f"Neue Version {version} verfügbar  (aktuell: {APP_VERSION})"
        )
        self._update_banner.setVisible(True)

    @Slot()
    def _start_install(self) -> None:
        if not self._pending_dmg_url:
            return
        reply = QMessageBox.question(
            self,
            "Update installieren",
            f"Das Update wird jetzt heruntergeladen und installiert.\n"
            f"Die App wird danach automatisch neu gestartet.\n\n"
            f"Jetzt fortfahren?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._install_btn.setEnabled(False)
        self._install_btn.setText("Wird installiert…")
        self._update_progress.setVisible(True)
        self._update_progress.setValue(0)
        self._sync_btn.setEnabled(False)

        worker = InstallWorker(self._pending_dmg_url)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(lambda m: self._log.append_line(m, "INFO"))
        worker.progress.connect(self._update_progress.setValue)
        worker.done.connect(self._on_install_done)
        worker.done.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        self._install_thread = thread
        thread.start()

    @Slot(bool)
    def _on_install_done(self, success: bool) -> None:
        if success:
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()
        else:
            self._install_btn.setEnabled(True)
            self._install_btn.setText("Jetzt aktualisieren")
            self._update_progress.setVisible(False)
            self._sync_btn.setEnabled(True)
