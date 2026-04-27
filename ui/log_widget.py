from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor


class LogWidget(QTextEdit):
    """Read-only log display with colour-coded levels."""

    COLORS = {
        "INFO": "#d4d4d4",
        "OK": "#4ec9b0",
        "WARN": "#dcdcaa",
        "ERROR": "#f44747",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setStyleSheet(
            "QTextEdit {"
            "  background-color: #1e1e1e;"
            "  font-family: Menlo, monospace;"
            "  font-size: 12px;"
            "  border: 1px solid #3c3c3c;"
            "  border-radius: 4px;"
            "  padding: 4px;"
            "}"
        )

    @Slot(str, str)
    def append_line(self, text: str, level: str = "INFO") -> None:
        color = self.COLORS.get(level, self.COLORS["INFO"])
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.toPlainText():
            cursor.insertText(text, fmt)
        else:
            cursor.insertText("\n" + text, fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def clear_log(self) -> None:
        self.clear()
