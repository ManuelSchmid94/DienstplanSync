"""
Dialog for reviewing and editing detected shifts before calendar export.
"""
import re
from datetime import date as date_type

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QDialogButtonBox, QMessageBox,
    QAbstractItemView,
)
from PySide6.QtCore import Qt

from core.models import Shift

_WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")

_COL_CHECK = 0
_COL_DATE = 1
_COL_TYPE = 2
_COL_START = 3
_COL_END = 4


class ShiftReviewDialog(QDialog):
    def __init__(self, shifts: list[Shift], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Erkannte Schichten prüfen")
        self.setMinimumSize(700, 480)
        self._shifts = shifts
        self._build_ui()
        self._apply_stylesheet()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(self._make_header())
        layout.addLayout(self._make_toolbar())
        layout.addWidget(self._make_table())
        layout.addWidget(self._make_buttons())

    def _make_header(self) -> QLabel:
        lbl = QLabel(
            f"<b>{len(self._shifts)}</b> Schicht(en) erkannt — "
            "Auswahl und Zeiten vor Übernahme in den Kalender prüfen."
        )
        lbl.setWordWrap(True)
        return lbl

    def _make_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for label, slot in [
            ("Alle auswählen", self._select_all),
            ("Keine auswählen", self._select_none),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("secondaryBtn")
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch()
        return row

    def _make_table(self) -> QTableWidget:
        self._table = QTableWidget(len(self._shifts), 5)
        self._table.setHorizontalHeaderLabels(["", "Datum", "Typ", "Beginn", "Ende"])
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.AnyKeyPressed
        )

        for row, shift in enumerate(self._shifts):
            # ── Checkbox ──────────────────────────────────────────────────────
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked)
            self._table.setItem(row, _COL_CHECK, chk)

            # ── Datum (read-only, ISO date stored in UserRole) ────────────────
            d = date_type.fromisoformat(shift.date)
            date_str = f"{_WEEKDAYS[d.weekday()]} {d.day:02d}.{d.month:02d}.{d.year}"
            date_item = QTableWidgetItem(date_str)
            date_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            date_item.setData(Qt.UserRole, shift.date)
            self._table.setItem(row, _COL_DATE, date_item)

            # ── Typ (editable) ────────────────────────────────────────────────
            self._table.setItem(row, _COL_TYPE, QTableWidgetItem(shift.type or ""))

            # ── Beginn / Ende (editable) ──────────────────────────────────────
            self._table.setItem(row, _COL_START, QTableWidgetItem(shift.start))
            self._table.setItem(row, _COL_END, QTableWidgetItem(shift.end))

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_DATE, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_TYPE, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_START, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_END, QHeaderView.ResizeToContents)

        return self._table

    def _make_buttons(self) -> QDialogButtonBox:
        box = QDialogButtonBox()
        ok_btn = box.addButton("In Kalender übernehmen", QDialogButtonBox.AcceptRole)
        ok_btn.setObjectName("primaryBtn")
        box.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        box.accepted.connect(self._on_accept)
        box.rejected.connect(self.reject)
        return box

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _select_all(self) -> None:
        for row in range(self._table.rowCount()):
            self._table.item(row, _COL_CHECK).setCheckState(Qt.Checked)

    def _select_none(self) -> None:
        for row in range(self._table.rowCount()):
            self._table.item(row, _COL_CHECK).setCheckState(Qt.Unchecked)

    def _on_accept(self) -> None:
        for row in range(self._table.rowCount()):
            if self._table.item(row, _COL_CHECK).checkState() != Qt.Checked:
                continue
            for col, label in [(_COL_START, "Beginn"), (_COL_END, "Ende")]:
                val = self._table.item(row, col).text().strip()
                if not _TIME_RE.match(val):
                    QMessageBox.warning(
                        self,
                        "Ungültige Uhrzeit",
                        f"Zeile {row + 1} - {label}: '{val}' ist kein gueltiges Format (HH:MM).",
                    )
                    return
        self.accept()

    # ── Result ────────────────────────────────────────────────────────────────

    def get_selected_shifts(self) -> list[Shift]:
        result = []
        for row in range(self._table.rowCount()):
            if self._table.item(row, _COL_CHECK).checkState() != Qt.Checked:
                continue
            iso_date = self._table.item(row, _COL_DATE).data(Qt.UserRole)
            shift_type = self._table.item(row, _COL_TYPE).text().strip() or None
            start = self._table.item(row, _COL_START).text().strip()
            end = self._table.item(row, _COL_END).text().strip()
            result.append(Shift(date=iso_date, start=start, end=end, type=shift_type))
        return result

    # ── Style ─────────────────────────────────────────────────────────────────

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #252526;
                color: #cccccc;
            }
            QLabel {
                color: #cccccc;
            }
            QTableWidget {
                background-color: #1e1e1e;
                alternate-background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                gridline-color: #3c3c3c;
                outline: none;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #9cdcfe;
                border: none;
                border-right: 1px solid #3c3c3c;
                border-bottom: 1px solid #3c3c3c;
                padding: 5px 8px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555;
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
            QPushButton#secondaryBtn {
                background-color: transparent;
                border-color: #555;
                color: #9cdcfe;
                font-size: 11px;
                padding: 3px 10px;
            }
            QScrollBar:vertical {
                background: #252526;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 5px;
                min-height: 20px;
            }
        """)
