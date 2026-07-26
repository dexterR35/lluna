"""Shared zoom control bar — used by ZoomableImageView and RetouchCanvas."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, ToolButton

from backend.config import tr
from ui.theme import PREVIEW


class ZoomChromeBar(QWidget):
    """Title (optional) + zoom % + out / in / fit / 100% — one chrome everywhere."""

    zoom_out_clicked = Signal()
    zoom_in_clicked = Signal()
    zoom_fit_clicked = Signal()
    zoom_actual_clicked = Signal()

    def __init__(self, parent=None, *, title: Optional[str] = None):
        super().__init__(parent)
        self.setObjectName("ZoomChromeBar")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(PREVIEW["zoom_gap"])

        p = PREVIEW
        self.title_label = BodyLabel(title or "", self)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        self.title_label.setStyleSheet(
            f"color: {p['title']}; font-size: {p['title_size']}px; "
            f"font-weight: {p['title_weight']}; background: transparent;"
        )
        self.title_label.setVisible(bool(title))
        row.addWidget(self.title_label, 0)
        row.addStretch(1)

        self.zoom_label = BodyLabel("", self)
        self.zoom_label.setMinimumWidth(p["zoom_label_min_w"])
        self.zoom_label.setStyleSheet(
            f"color: {p['content']}; font-size: {p['content_size']}px; "
            f"background: transparent;"
        )
        self.zoom_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.zoom_label)

        bg = tr["BgRemove"]
        for icon, tip_key, tip_fallback, signal in (
            (FluentIcon.ZOOM_OUT, "ZoomOut", "Zoom out", self.zoom_out_clicked),
            (FluentIcon.ZOOM_IN, "ZoomIn", "Zoom in", self.zoom_in_clicked),
            (FluentIcon.FIT_PAGE, "ZoomFit", "Fit to view", self.zoom_fit_clicked),
            (FluentIcon.ZOOM, "ZoomActual", "Actual size (100%)", self.zoom_actual_clicked),
        ):
            btn = ToolButton(icon, self)
            btn.setToolTip(bg.get(tip_key, tip_fallback))
            btn.clicked.connect(signal.emit)
            row.addWidget(btn)

    def set_title(self, title: str):
        self.title_label.setText(title)
        self.title_label.setVisible(bool(title))

    def set_zoom_text(self, text: str):
        self.zoom_label.setText(text)
