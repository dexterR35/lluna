"""Reusable Before / After dual-pane image preview (Remove BG + Video image mode).

Empty state uses the shared UploadDropPanel. As soon as an image is shown
(or replaced), the layout switches to side-by-side Before / After.
"""

from __future__ import annotations

from typing import Optional

from PIL import Image
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from backend.config import tr
from ui.component.preview.upload_drop_panel import UploadDropPanel
from ui.component.preview.zoomable_image_view import ZoomableImageView
from ui.theme import PAGE


class BeforeAfterPreview(QWidget):
    """Full empty upload pane, then equal Before/After zoom panes."""

    empty_clicked = Signal()
    files_dropped = Signal(list)

    def __init__(
        self,
        *,
        upload_hint: str = "",
        before_title: str = "Before",
        after_title: str = "After",
        after_placeholder: Optional[str] = None,
        formats_hint: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("BeforeAfterPreview")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._before_title = before_title
        self._after_title = after_title
        self._upload_hint = upload_hint
        self._after_placeholder = after_placeholder if after_placeholder is not None else after_title

        bg = tr["BgRemove"]
        formats = formats_hint if formats_hint is not None else bg.get("UploadFormatsImage", "")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget(self)
        root.addWidget(self.stack, 1)

        # --- Full Preview drop zone (shared with Video empty) ---
        self.empty_view = UploadDropPanel(formats_hint=formats, parent=self)
        self.empty_view.empty_clicked.connect(self.empty_clicked.emit)
        self.empty_view.files_dropped.connect(self.files_dropped.emit)
        self.stack.addWidget(self.empty_view)

        # --- Before | After once an image is present ---
        self.split_page = QWidget(self)
        split = QHBoxLayout(self.split_page)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(PAGE["spacing"])

        self.before_view = ZoomableImageView(
            before_title,
            self.split_page,
            accept_file_drops=True,
        )
        self.after_view = ZoomableImageView(self._after_placeholder, self.split_page)
        self.before_view.files_dropped.connect(self.files_dropped.emit)

        split.addWidget(self.before_view, 1)
        split.addWidget(self.after_view, 1)
        self.stack.addWidget(self.split_page)

        self.show_empty()

    def _show_split(self):
        self.stack.setCurrentWidget(self.split_page)

    def show_empty(self, hint: Optional[str] = None):
        if hint is not None:
            self._upload_hint = hint
        self.empty_view.clear()
        self.before_view.clear(self._before_title)
        self.before_view.set_title(self._before_title)
        self.hide_after()
        self.stack.setCurrentWidget(self.empty_view)

    def show_before(self, path: str, *, on_error_hint: Optional[str] = None):
        self._show_split()
        try:
            self.before_view.set_title(self._before_title)
            self.before_view.set_rgb_path(path)
        except Exception:
            self.before_view.set_title(self._upload_hint or self._before_title)
            self.before_view.clear(on_error_hint or path)

    def show_before_rgba(self, rgba: Image.Image):
        self._show_split()
        self.before_view.set_title(self._before_title)
        self.before_view.set_rgba_image(rgba)

    def show_after_loading(self, loading_text: str):
        self._show_split()
        self.after_view.set_title(self._after_title)
        self.after_view.clear(loading_text)

    def show_after_rgba(self, rgba: Image.Image):
        self._show_split()
        self.after_view.set_title(self._after_title)
        self.after_view.set_rgba_image(rgba)

    def show_after_path(self, path: str, *, rgba: bool = False):
        self._show_split()
        self.after_view.set_title(self._after_title)
        if rgba:
            self.after_view.set_rgba_image(Image.open(path).convert("RGBA"))
        else:
            self.after_view.set_rgb_path(path)

    def hide_after(self):
        self.after_view.set_title(self._after_title)
        self.after_view.clear(self._after_placeholder)

    def set_after_error(self, message: str):
        self._show_split()
        self.after_view.set_title(self._after_title)
        self.after_view.clear(message)
