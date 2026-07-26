"""Scrollable image preview with zoom buttons and Ctrl+wheel zoom-to-cursor."""

from __future__ import annotations

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, Signal, QPoint, QEvent, QRect
from PySide6.QtGui import QImage, QPixmap, QWheelEvent, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QFrame,
)
from qfluentwidgets import qconfig

from backend.config import config
from ui.component.preview.zoom_chrome import ZoomChromeBar
from ui.theme import PREVIEW


def _preview_chrome_qss() -> tuple[str, str, str]:
    """Scroll area, viewport, and label styles (outer border is painted)."""
    p = PREVIEW
    return (
        f"QScrollArea {{ background: {p['bg']}; border: none; }}",
        f"background: {p['bg']}; border: none;",
        f"color: {p['content']}; background: transparent;",
    )


def _display_max_side(max_side: int | None) -> int:
    """Effective display cap. 0 / negative = original size (no downsample)."""
    if max_side is None:
        max_side = config.previewMaxSide
    return int(max_side) if max_side else 0


def rgb_pixmap_from_path(path: str, max_side: int | None = None) -> QPixmap:
    """Load RGB at original size unless max_side > 0 caps the longest edge (display only)."""
    cap = _display_max_side(max_side)
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if cap > 0:
        scale = min(1.0, cap / max(w, h))
        if scale < 1.0:
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.BILINEAR,
            )
            w, h = img.size
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, w, h, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


def checkerboard_pixmap_from_rgba(rgba: Image.Image, max_side: int | None = None) -> QPixmap:
    """Composite RGBA onto a checkerboard at original size (or optional display cap)."""
    cap = _display_max_side(max_side)
    img = rgba.convert("RGBA")
    w, h = img.size
    if cap > 0:
        scale = min(1.0, cap / max(w, h))
        if scale < 1.0:
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.BILINEAR,
            )
            w, h = img.size

    tile = max(1, int(config.checkerboardTile))
    # Vectorized checker - avoid slow advanced indexing on large images
    yy = np.arange(h, dtype=np.int32)[:, None]
    xx = np.arange(w, dtype=np.int32)[None, :]
    parity = (((xx // tile) + (yy // tile)) & 1).astype(np.uint8)
    c0 = np.asarray(PREVIEW["checker_a"][:3], dtype=np.uint8)
    c1 = np.asarray(PREVIEW["checker_b"][:3], dtype=np.uint8)
    bg = np.where(parity[..., None] == 0, c0, c1)

    fg = np.asarray(img, dtype=np.uint8)
    a = fg[:, :, 3:4].astype(np.uint16)
    # Integer alpha blend: out = (fg*a + bg*(255-a)) / 255
    out_rgb = (
        (fg[:, :, :3].astype(np.uint16) * a + bg.astype(np.uint16) * (255 - a)) // 255
    ).astype(np.uint8)
    rgba_out = np.empty((h, w, 4), dtype=np.uint8)
    rgba_out[:, :, :3] = out_rgb
    rgba_out[:, :, 3] = 255
    rgba_out = np.ascontiguousarray(rgba_out)
    qimg = QImage(rgba_out.data, w, h, 4 * w, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class ZoomableImageView(QWidget):
    """
    Image viewer with zoom chrome and optional subtitle-region selection.
    Selection rects are ratio coords (ymin, ymax, xmin, xmax) in 0..1.
    Empty drag/browse UI lives in UploadDropPanel (shared for video + image).
    """

    zoom_changed = Signal(float)
    empty_clicked = Signal()
    files_dropped = Signal(list)
    selections_changed = Signal(list)

    def __init__(
        self,
        title: str = "",
        parent=None,
        *,
        accept_file_drops: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("ZoomableImageView")
        self._source: QPixmap | None = None
        self._zoom = 1.0
        self._fit_mode = True
        self._panning = False
        self._pan_last = None
        self._placeholder = title or ""
        self._radius = PREVIEW["radius"]
        self._accept_file_drops = bool(accept_file_drops)
        self._selection_enabled = False
        self._selection_rects: list[tuple[float, float, float, float]] = []
        self._active_selection = -1
        self._drawing = False
        self._drag_start: tuple[float, float] | None = None
        self._draft_rect: tuple[float, float, float, float] | None = None
        self._hovered = False
        self._drag_over = False
        self.image_label = None  # set later - eventFilter must tolerate None
        self.scroll = None

        root = QVBoxLayout(self)
        root.setContentsMargins(PREVIEW["pad"], PREVIEW["pad"], PREVIEW["pad"], PREVIEW["pad"])
        root.setSpacing(PREVIEW["spacing"])

        self._header_host = ZoomChromeBar(self, title=title)
        self.title_label = self._header_host.title_label
        self.zoom_label = self._header_host.zoom_label
        self._header_host.zoom_out_clicked.connect(self.zoom_out)
        self._header_host.zoom_in_clicked.connect(self.zoom_in)
        self._header_host.zoom_fit_clicked.connect(self.zoom_fit)
        self._header_host.zoom_actual_clicked.connect(self.zoom_actual)
        root.addWidget(self._header_host)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setMinimumHeight(PREVIEW["min_h"])
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.image_label = QLabel(self._placeholder)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setCursor(Qt.PointingHandCursor)
        self.scroll.setWidget(self.image_label)
        root.addWidget(self.scroll, 1)

        self._apply_preview_chrome()
        qconfig.themeChanged.connect(lambda *_: self._apply_preview_chrome())

        self.scroll.viewport().installEventFilter(self)
        self.image_label.installEventFilter(self)
        self.setMouseTracking(True)
        self.scroll.setMouseTracking(True)
        self.image_label.setMouseTracking(True)
        if self._accept_file_drops:
            self.setAcceptDrops(True)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def set_selection_enabled(self, enabled: bool):
        self._selection_enabled = bool(enabled)
        if not enabled:
            self.clear_selections()
        else:
            self._render()

    def set_selection_rects(self, rects: list):
        self._selection_rects = [tuple(r) for r in (rects or [])]
        self._active_selection = len(self._selection_rects) - 1 if self._selection_rects else -1
        self._draft_rect = None
        self._render()

    def get_selection_rects(self) -> list:
        return list(self._selection_rects)

    def clear_selections(self):
        self._selection_rects = []
        self._active_selection = -1
        self._draft_rect = None
        self._drawing = False
        self._drag_start = None
        self._render()
        self.selections_changed.emit(self._selection_rects)

    def ratios_to_pixels(self, width: int, height: int) -> list[tuple[int, int, int, int]]:
        out = []
        for ymin, ymax, xmin, xmax in self._selection_rects:
            y0, y1 = sorted((ymin, ymax))
            x0, x1 = sorted((xmin, xmax))
            out.append((
                max(0, int(y0 * height)),
                min(height, int(y1 * height)),
                max(0, int(x0 * width)),
                min(width, int(x1 * width)),
            ))
        return out

    def _apply_preview_chrome(self):
        scroll_qss, viewport_qss, label_qss = _preview_chrome_qss()
        self.scroll.setStyleSheet(scroll_qss)
        self.scroll.viewport().setStyleSheet(viewport_qss)
        self.image_label.setStyleSheet(label_qss)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        p = PREVIEW
        bg = QColor(p["bg"])
        if self._drag_over and self._accept_file_drops:
            border = QColor(p["border_active"])
            pen = QPen(border, p["border_width_active"])
            pen.setStyle(Qt.PenStyle.SolidLine)
        else:
            border = QColor(p["border"])
            pen = QPen(border, p["border_width"])
            pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setBrush(bg)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), self._radius, self._radius)
        super().paintEvent(event)

    def dragEnterEvent(self, event):
        if not self._accept_file_drops:
            event.ignore()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drag_over = True
            self.update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drag_over = False
        self.update()
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        if self._accept_file_drops and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        self._drag_over = False
        self.update()
        if not self._accept_file_drops:
            event.ignore()
            return
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                paths.append(path)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def eventFilter(self, obj, event):
        # Guard: filters can fire during construction / teardown
        image_label = getattr(self, "image_label", None)
        scroll = getattr(self, "scroll", None)
        if image_label is None or scroll is None:
            return False

        et = event.type()
        if et == QEvent.Type.Wheel and obj in (scroll.viewport(), image_label):
            self._handle_wheel(event)
            return True
        if obj == image_label:
            if self._selection_enabled and self._source is not None:
                if et == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                    return self._selection_press(event)
                if et == QEvent.Type.MouseMove and self._drawing:
                    return self._selection_move(event)
                if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
                    return self._selection_release(event)
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                if self._source is None:
                    self.empty_clicked.emit()
                    return True
                if not self._fit_mode and self._source is not None and not self._selection_enabled:
                    self._panning = True
                    self._pan_last = event.globalPosition().toPoint()
                    image_label.setCursor(Qt.ClosedHandCursor)
                    return True
            elif et == QEvent.Type.MouseMove and self._panning and self._pan_last is not None:
                pos = event.globalPosition().toPoint()
                delta = pos - self._pan_last
                self._pan_last = pos
                hbar = scroll.horizontalScrollBar()
                vbar = scroll.verticalScrollBar()
                hbar.setValue(hbar.value() - delta.x())
                vbar.setValue(vbar.value() - delta.y())
                return True
            elif et == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
                self._panning = False
                self._pan_last = None
                image_label.setCursor(
                    Qt.OpenHandCursor if not self._fit_mode and not self._selection_enabled else Qt.ArrowCursor
                )
                return True
        return super().eventFilter(obj, event)

    def _label_ratio(self, event) -> tuple[float, float]:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        w = max(1, self.image_label.width())
        h = max(1, self.image_label.height())
        return (
            max(0.0, min(1.0, pos.y() / h)),
            max(0.0, min(1.0, pos.x() / w)),
        )

    def _selection_press(self, event) -> bool:
        y, x = self._label_ratio(event)
        self._drawing = True
        self._drag_start = (y, x)
        self._draft_rect = (y, y, x, x)
        self._active_selection = -1
        self.image_label.setCursor(Qt.CrossCursor)
        self._render()
        return True

    def _selection_move(self, event) -> bool:
        if not self._drag_start:
            return True
        y, x = self._label_ratio(event)
        y0, x0 = self._drag_start
        self._draft_rect = (y0, y, x0, x)
        self._render()
        return True

    def _selection_release(self, event) -> bool:
        if not self._drawing or not self._draft_rect:
            self._drawing = False
            return True
        ymin, ymax, xmin, xmax = self._draft_rect
        y0, y1 = sorted((ymin, ymax))
        x0, x1 = sorted((xmin, xmax))
        self._drawing = False
        self._drag_start = None
        self._draft_rect = None
        if (y1 - y0) > 0.01 and (x1 - x0) > 0.01:
            if event.modifiers() & Qt.ControlModifier:
                self._selection_rects.append((y0, y1, x0, x1))
            else:
                self._selection_rects = [(y0, y1, x0, x1)]
            self._active_selection = len(self._selection_rects) - 1
            self.selections_changed.emit(self._selection_rects)
        self.image_label.setCursor(Qt.ArrowCursor)
        self._render()
        return True

    def _viewport_pos_from_wheel(self, event: QWheelEvent) -> QPoint:
        gp = event.globalPosition().toPoint()
        return self.scroll.viewport().mapFromGlobal(gp)

    def _handle_wheel(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta == 0 or self._source is None:
            return
        factor = config.zoomStep if delta > 0 else (1.0 / config.zoomStep)
        self._zoom_toward(factor, self._viewport_pos_from_wheel(event))

    def _zoom_toward(self, factor: float, viewport_pos: QPoint):
        if self._source is None:
            return
        old_zoom = self._current_display_zoom()
        new_zoom = max(config.minZoom, min(config.maxZoom, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-6:
            return

        label_pos = self.image_label.mapFrom(self.scroll.viewport(), viewport_pos)
        old_w = max(1, self.image_label.width())
        old_h = max(1, self.image_label.height())
        rx = max(0.0, min(1.0, label_pos.x() / old_w))
        ry = max(0.0, min(1.0, label_pos.y() / old_h))

        self._fit_mode = False
        self._zoom = new_zoom
        self._render()

        new_w = max(1, self.image_label.width())
        new_h = max(1, self.image_label.height())
        target = QPoint(int(rx * new_w), int(ry * new_h))
        global_target = self.image_label.mapTo(self.scroll.viewport(), target)
        hbar = self.scroll.horizontalScrollBar()
        vbar = self.scroll.verticalScrollBar()
        hbar.setValue(hbar.value() + global_target.x() - viewport_pos.x())
        vbar.setValue(vbar.value() + global_target.y() - viewport_pos.y())
        self.image_label.setCursor(
            Qt.OpenHandCursor if not self._selection_enabled else Qt.ArrowCursor
        )
        self.zoom_changed.emit(self._zoom)

    def set_title(self, title: str):
        self._placeholder = title or ""
        self.title_label.setText(self._placeholder)
        if self._source is None:
            self.image_label.setText(self._placeholder)

    def clear(self, placeholder: str | None = None):
        self._source = None
        self._zoom = 1.0
        self._fit_mode = True
        text = placeholder if placeholder is not None else self._placeholder
        if placeholder is not None:
            self._placeholder = placeholder
            self.title_label.setText(placeholder)
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText(text)
        self.image_label.resize(self.scroll.viewport().size())
        self.image_label.setCursor(Qt.PointingHandCursor)
        self._update_zoom_label()
        self.update()

    def set_pixmap(self, pixmap: QPixmap | None, fit: bool = True):
        if pixmap is None or pixmap.isNull():
            self.clear()
            return
        self._source = pixmap
        self.image_label.setText("")
        if fit:
            self.zoom_fit()
        else:
            self._render()
        self.update()

    def set_rgb_path(self, path: str, max_side: int | None = None):
        self.set_pixmap(rgb_pixmap_from_path(path, max_side=max_side), fit=True)

    def set_rgba_image(self, rgba: Image.Image, max_side: int | None = None):
        self.set_pixmap(checkerboard_pixmap_from_rgba(rgba, max_side=max_side), fit=True)

    def zoom_in(self):
        center = self.scroll.viewport().rect().center()
        self._zoom_toward(config.zoomStep, center)

    def zoom_out(self):
        center = self.scroll.viewport().rect().center()
        self._zoom_toward(1.0 / config.zoomStep, center)

    def zoom_fit(self):
        if self._source is None:
            self._update_zoom_label()
            return
        self._fit_mode = True
        self._render()
        self.image_label.setCursor(Qt.ArrowCursor)
        self.zoom_changed.emit(self._zoom)

    def zoom_actual(self):
        center = self.scroll.viewport().rect().center()
        old = self._current_display_zoom()
        if old <= 0:
            return
        self._zoom_toward(1.0 / old, center)

    def _current_display_zoom(self) -> float:
        if self._fit_mode and self._source is not None:
            return self._fit_scale()
        return self._zoom

    def _fit_scale(self) -> float:
        if self._source is None or self._source.isNull():
            return 1.0
        vp = self.scroll.viewport().size()
        if vp.width() <= 1 or vp.height() <= 1:
            return 1.0
        sx = vp.width() / max(1, self._source.width())
        sy = vp.height() / max(1, self._source.height())
        return max(config.minZoom, min(sx, sy, config.maxZoom))

    def _update_zoom_label(self):
        if self._source is None:
            self._header_host.set_zoom_text("")
            return
        if self._fit_mode:
            pct = int(round(self._fit_scale() * 100))
            self._header_host.set_zoom_text(f"Fit {pct}%")
        else:
            self._header_host.set_zoom_text(f"{int(round(self._zoom * 100))}%")

    def _draw_selection_overlay(self, pixmap: QPixmap) -> QPixmap:
        if not self._selection_enabled:
            return pixmap
        rects = list(self._selection_rects)
        if self._draft_rect is not None:
            rects = rects + [self._draft_rect]
        if not rects:
            return pixmap
        out = pixmap.copy()
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = out.width(), out.height()
        for i, rect in enumerate(rects):
            ymin, ymax, xmin, xmax = rect
            y0, y1 = sorted((ymin, ymax))
            x0, x1 = sorted((xmin, xmax))
            is_active = (i == self._active_selection) or (
                self._draft_rect is not None and i == len(rects) - 1
            )
            pen = QPen(
                QColor(PREVIEW["selection_active"])
                if is_active
                else QColor(PREVIEW["selection_idle"])
            )
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(QRect(
                int(x0 * w),
                int(y0 * h),
                max(1, int((x1 - x0) * w)),
                max(1, int((y1 - y0) * h)),
            ))
        painter.end()
        return out

    def _render(self):
        if self._source is None or self._source.isNull():
            return
        scale = self._fit_scale() if self._fit_mode else self._zoom
        if self._fit_mode:
            self._zoom = scale

        w = max(1, int(self._source.width() * scale))
        h = max(1, int(self._source.height() * scale))
        scaled = self._source.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scaled = self._draw_selection_overlay(scaled)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self._update_zoom_label()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self._source is not None:
            self._render()
        elif self._source is None:
            self.image_label.resize(self.scroll.viewport().size())
