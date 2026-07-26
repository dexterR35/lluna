"""Midgard range sliders — solid primary thumb, simple track."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSlider
from qfluentwidgets.components.widgets.slider import Slider, SliderHandle

from ui.theme import SLIDER


class _PrimarySliderHandle(SliderHandle):
    """Solid primary circle — no outer ring or inner dot."""

    def __init__(self, parent: QSlider):
        super().__init__(parent)
        side = SLIDER["handle"]
        self.setFixedSize(side, side)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def mousePressEvent(self, e):
        self.pressed.emit()

    def mouseReleaseEvent(self, e):
        self.released.emit()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(SLIDER["handle_color"]))
        c = self.width() // 2
        r = self.width() // 2 - 1
        painter.drawEllipse(QPoint(c, c), r, r)


class PrimarySlider(Slider):
    """Fluent slider with Midgard primary-only chrome."""

    def _postInit(self):
        self.handle = _PrimarySliderHandle(self)
        self._pressedPos = QPoint()
        self.setOrientation(self.orientation())
        self.handle.pressed.connect(self.sliderPressed)
        self.handle.released.connect(self.sliderReleased)
        self.valueChanged.connect(self._adjustHandlePos)

    def setOrientation(self, orientation: Qt.Orientation) -> None:
        super().setOrientation(orientation)
        h = SLIDER["handle"]
        if orientation == Qt.Orientation.Horizontal:
            self.setMinimumHeight(h)
        else:
            self.setMinimumWidth(h)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.orientation() == Qt.Orientation.Horizontal:
            self._drawHorizonGroove(painter)
        else:
            self._drawVerticalGroove(painter)

    def _drawHorizonGroove(self, painter: QPainter):
        w, r = self.width(), self.handle.width() / 2
        gh = SLIDER["groove_h"]
        y = r - gh / 2
        painter.setBrush(QColor(SLIDER["track"]))
        painter.drawRoundedRect(QRectF(r, y, w - r * 2, gh), gh / 2, gh / 2)

        if self.maximum() - self.minimum() == 0:
            return

        painter.setBrush(QColor(SLIDER["fill"]))
        aw = (self.value() - self.minimum()) / (self.maximum() - self.minimum()) * (w - r * 2)
        painter.drawRoundedRect(QRectF(r, y, aw, gh), gh / 2, gh / 2)

    def _drawVerticalGroove(self, painter: QPainter):
        h, r = self.height(), self.handle.width() / 2
        gw = SLIDER["groove_h"]
        x = r - gw / 2
        painter.setBrush(QColor(SLIDER["track"]))
        painter.drawRoundedRect(QRectF(x, r, gw, h - 2 * r), gw / 2, gw / 2)

        if self.maximum() - self.minimum() == 0:
            return

        painter.setBrush(QColor(SLIDER["fill"]))
        ah = (self.value() - self.minimum()) / (self.maximum() - self.minimum()) * (h - r * 2)
        painter.drawRoundedRect(QRectF(x, r, gw, ah), gw / 2, gw / 2)
