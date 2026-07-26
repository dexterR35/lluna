"""Stacked media preview for the Video tab: empty / image before-after / video."""

from __future__ import annotations

import os
from enum import Enum, auto

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from backend.config import tr
from ui.component.preview.before_after_preview import BeforeAfterPreview
from ui.component.preview.upload_drop_panel import UploadDropPanel
from ui.component.preview.video_display_component import VideoDisplayComponent


class MediaPreviewMode(Enum):
    EMPTY = auto()
    IMAGE = auto()
    VIDEO = auto()


class MediaPreviewHost(QWidget):
    """
    Shared UploadDropPanel empty state, equal Before/After for images, or video preview.
    """

    empty_clicked = Signal()
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MediaPreviewHost")
        self._mode = MediaPreviewMode.EMPTY

        gui = tr["SubtitleExtractorGUI"]
        self._upload_hint = gui.get("SelectMediaTitle", gui.get("UploadImageOrVideo", "Upload image or video"))
        self._before_title = gui.get("Before", "Before")
        self._after_title = gui.get("After", "After")
        self._after_loading = gui.get("AfterLoading", "Removing subtitles…")
        self._formats_hint = gui.get("UploadFormatsMedia", "")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget(self)
        root.addWidget(self.stack, 1)

        # --- Empty: same UploadDropPanel as Remove BG / image entry ---
        self.empty_view = UploadDropPanel(formats_hint=self._formats_hint, parent=self)
        self.empty_view.empty_clicked.connect(self.empty_clicked.emit)
        self.empty_view.files_dropped.connect(self.files_dropped.emit)
        self.stack.addWidget(self.empty_view)

        # --- Image: Before/After (drops still use shared empty or Before pane) ---
        self.image_preview = BeforeAfterPreview(
            upload_hint=gui.get("SelectImageTitle", self._upload_hint),
            before_title=self._before_title,
            after_title=self._after_title,
            after_placeholder=self._after_title,
            formats_hint=self._formats_hint,
            parent=self,
        )
        self.image_preview.before_view.set_selection_enabled(True)
        self.image_preview.empty_clicked.connect(self.empty_clicked.emit)
        self.image_preview.files_dropped.connect(self.files_dropped.emit)
        self.stack.addWidget(self.image_preview)

        # --- Video: classic player only ---
        self.video_page = QWidget(self)
        video_layout = QVBoxLayout(self.video_page)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)
        self.video_display = VideoDisplayComponent(self.video_page)
        video_layout.addWidget(self.video_display, 1)
        self.stack.addWidget(self.video_page)

        self.show_empty()

    @property
    def mode(self) -> MediaPreviewMode:
        return self._mode

    @property
    def video_slider(self):
        return self.video_display.video_slider

    @property
    def before_view(self):
        return self.image_preview.before_view

    @property
    def after_view(self):
        return self.image_preview.after_view

    def show_empty(self):
        self._mode = MediaPreviewMode.EMPTY
        self.video_display.pause()
        self.video_display.clear_preview()
        self.image_preview.show_empty(self._upload_hint)
        self.empty_view.clear()
        self.stack.setCurrentWidget(self.empty_view)

    def show_video(self):
        self._mode = MediaPreviewMode.VIDEO
        self.video_display.set_controls_visible(True)
        self.stack.setCurrentWidget(self.video_page)

    def show_image(self, path: str | None = None):
        self._mode = MediaPreviewMode.IMAGE
        self.video_display.pause()
        if path:
            self.image_preview.show_before(
                path,
                on_error_hint=tr["SubtitleExtractorGUI"].get("OpenVideoFailed", "{}").format(path),
            )
        self.stack.setCurrentWidget(self.image_preview)

    def hide_after(self):
        self.image_preview.hide_after()

    def show_after_loading(self):
        self.image_preview.show_after_loading(self._after_loading)

    def show_after_path(self, path: str) -> bool:
        if not path or not os.path.isfile(path):
            self.hide_after()
            return False
        try:
            self.image_preview.show_after_path(path, rgba=False)
            return True
        except Exception:
            self.hide_after()
            return False
