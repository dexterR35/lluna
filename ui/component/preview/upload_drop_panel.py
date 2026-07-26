"""Shared full-area drag / browse upload drop zone (Video + Image + Remove BG)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEvent, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, Theme, qconfig

from backend.config import tr
from ui.theme import PREVIEW


def _panel_qss() -> str:
    p = PREVIEW
    return f"""
        QWidget#UploadDropPanel {{
            background: transparent;
        }}
        QLabel#UploadIconBadge {{
            background-color: {p['badge_bg']};
            border: 1px solid {p['badge_border']};
            border-radius: {p['radius']}px;
            min-width: {p['badge_size']}px;
            max-width: {p['badge_size']}px;
            min-height: {p['badge_size']}px;
            max-height: {p['badge_size']}px;
        }}
        QLabel#UploadEmptyTitle {{
            color: {p['title']};
            font-size: {p['title_size']}px;
            font-weight: {p['title_weight']};
        }}
        QLabel#UploadEmptyTitle a {{
            color: {p['link']};
            text-decoration: underline;
            font-weight: {p['link_weight']};
        }}
        QLabel#UploadEmptyFormats {{
            color: {p['content']};
            font-size: {p['content_size']}px;
        }}
    """


def _drag_drop_title_html() -> str:
    bg = tr["BgRemove"]
    gui = tr["SubtitleExtractorGUI"]
    lead = bg.get("DragDropLead") or gui.get("DragDropLead", "Drag and Drop or")
    browse = bg.get("DragDropBrowse") or gui.get("DragDropBrowse", "Browse")
    tail = bg.get("DragDropTail") or gui.get("DragDropTail", "to Upload")
    return f'{lead} <a href="browse">{browse}</a> {tail}'


class UploadDropPanel(QWidget):
    """
    Full Preview empty state: dashed drop zone, upload icon, Browse link, formats.
    Same component / style for video and image entry points.
    """

    empty_clicked = Signal()
    files_dropped = Signal(list)

    def __init__(self, formats_hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("UploadDropPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.ArrowCursor)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self._formats_hint = formats_hint or ""
        self._radius = PREVIEW["radius"]
        self._hovered = False
        self._drag_over = False

        root = QVBoxLayout(self)
        root.setContentsMargins(
            PREVIEW["upload_pad"],
            PREVIEW["upload_pad"],
            PREVIEW["upload_pad"],
            PREVIEW["upload_pad"],
        )
        root.setSpacing(PREVIEW["spacing"])
        root.addStretch(1)

        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        self._badge = QLabel(self)
        self._badge.setObjectName("UploadIconBadge")
        self._badge.setAlignment(Qt.AlignCenter)
        badge_row.addWidget(self._badge)
        badge_row.addStretch(1)
        root.addLayout(badge_row)

        self._title = QLabel(self)
        self._title.setObjectName("UploadEmptyTitle")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setTextFormat(Qt.TextFormat.RichText)
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._title.setOpenExternalLinks(False)
        self._title.linkActivated.connect(lambda *_: self.empty_clicked.emit())
        root.addWidget(self._title)

        self._formats = QLabel(self._formats_hint, self)
        self._formats.setObjectName("UploadEmptyFormats")
        self._formats.setAlignment(Qt.AlignCenter)
        self._formats.setWordWrap(True)
        root.addWidget(self._formats)
        root.addStretch(1)

        self._badge.installEventFilter(self)
        self._formats.installEventFilter(self)
        self._apply_chrome()
        qconfig.themeChanged.connect(lambda *_: self._apply_chrome())

    def set_formats_hint(self, text: str):
        self._formats_hint = text or ""
        self._formats.setText(self._formats_hint)
        self._formats.setVisible(bool(self._formats_hint))

    def clear(self, *_args, **_kwargs):
        """Reset chrome (API-compatible with prior ZoomableImageView empty clears)."""
        self._apply_chrome()

    def set_title(self, *_args, **_kwargs):
        """Title is always the shared drag/browse copy."""
        self._title.setText(_drag_drop_title_html())

    def _refresh_icon(self):
        icon_enum = getattr(FluentIcon, "UP", None) or FluentIcon.ADD
        size = PREVIEW["upload_icon"]
        color = QColor(PREVIEW["badge_icon"])
        pix = icon_enum.icon(Theme.DARK, color=color).pixmap(size, size)
        self._badge.setPixmap(pix)
        self._badge.setFixedSize(QSize(PREVIEW["badge_size"], PREVIEW["badge_size"]))

    def _apply_chrome(self):
        self.setStyleSheet(_panel_qss())
        self._title.setText(_drag_drop_title_html())
        self._formats.setText(self._formats_hint)
        self._formats.setVisible(bool(self._formats_hint))
        self._refresh_icon()
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.setCursor(Qt.PointingHandCursor)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.setCursor(Qt.ArrowCursor)
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.empty_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if obj in (self._badge, self._formats) and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.empty_clicked.emit()
                return True
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        p = PREVIEW
        active = self._hovered or self._drag_over
        border = QColor(p["border_active"] if active else p["border"])
        pen = QPen(
            border,
            p["border_width_active"] if active else p["border_width_dash"],
        )
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern(list(p["dash"]))
        painter.setBrush(QColor(p["bg"]))
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), self._radius, self._radius)
        super().paintEvent(event)

    def dragEnterEvent(self, event):
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
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        self._drag_over = False
        self.update()
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
