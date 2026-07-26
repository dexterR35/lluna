"""Reusable colored log / output panel (content only — outer card is SectionCard)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QFrame, QSizePolicy, QTextEdit, QVBoxLayout, QWidget

from backend.tools import diag
from ui.theme import STATUS, TEXT, TEXT_SECONDARY, WORKSPACE


class LogPanel(QWidget):
    """Timestamped, colorized HTML log with optional auto-scroll."""

    def __init__(self, parent=None, minimum_height: int | None = None):
        super().__init__(parent)
        self.auto_scroll = True
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Plain QTextEdit — Fluent TextEdit paints its own nested card chrome.
        self.output_text = QTextEdit()
        self.output_text.setFrameShape(QFrame.Shape.NoFrame)
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(
            WORKSPACE["log_min_h"] if minimum_height is None else minimum_height
        )
        self.output_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.output_text.document().setDocumentMargin(2)
        self.output_text.setStyleSheet(
            f"QTextEdit {{ border: none; background: transparent; color: {TEXT}; }}"
        )
        self.output_text.viewport().setAutoFillBackground(False)
        self.output_text.verticalScrollBar().valueChanged.connect(self._on_scroll_change)
        layout.addWidget(self.output_text)

    def _on_scroll_change(self, value):
        scrollbar = self.output_text.verticalScrollBar()
        if value == scrollbar.maximum():
            self.auto_scroll = True
        elif self.auto_scroll and value < scrollbar.maximum():
            self.auto_scroll = False

    def append(self, *args):
        text = " ".join(str(a) for a in args).rstrip()
        timestamp = datetime.now().strftime("%H:%M:%S")
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if "Error" in text or "Failed" in text:
            color = STATUS["error"]
            if diag.is_enabled():
                diag.error(text)
            else:
                print(*args)
        elif "Success" in text or "Complete" in text or "Finished" in text:
            color = STATUS["success"]
            if diag.is_enabled():
                diag.event(text)
            else:
                print(*args)
        elif "Warning" in text:
            color = STATUS["warning"]
            if diag.is_enabled():
                diag.warn(text)
            else:
                print(*args)
        else:
            color = STATUS["info"]
            if diag.is_enabled():
                diag.event(text)
            else:
                print(*args)
        ts = TEXT_SECONDARY
        html = (
            f'<span style="color:{ts};">[{timestamp}]</span> '
            f'<span style="color:{color};">{escaped}</span><br>'
        )
        self.output_text.append(html)
        if self.auto_scroll:
            sb = self.output_text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear(self):
        self.output_text.clear()
        self.auto_scroll = True
