
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, FluentIcon, ProgressBar

from ui.component.controls.button_styles import ClickThrottle, make_button, make_stop_button
from ui.component.utils.confirm_dialog import ask_confirm
from ui.theme import (
    BUTTON_SIZE_MEDIUM,
    BUTTON_SIZES,
    FORM,
    SECTION,
    TEXT,
    WORKSPACE,
)

_GAP = SECTION["spacing"]
_MARGIN = SECTION["pad"]
_CLICK_THROTTLE_MS = 450
_BTN_H = BUTTON_SIZES[BUTTON_SIZE_MEDIUM]["height"]
_BTN_ICON = BUTTON_SIZES[BUTTON_SIZE_MEDIUM]["icon"]


@dataclass(frozen=True)
class RailActions:
    """Right-rail action labels / confirms - same component, different data per tab."""

    open_text: str
    run_text: str
    stop_text: str
    stop_confirm_title: str
    stop_confirm_desc: str
    reset_text: str
    reset_confirm_title: str
    reset_confirm_desc: str
    empty_list_hint: str = ""
    save_text: Optional[str] = None
    retouch_text: Optional[str] = None
    enhance_text: Optional[str] = None
    compare_text: Optional[str] = None
    settings_title: Optional[str] = None
    progress_label: Optional[str] = None  # e.g. "Processing {}%"


class ActionBar(CardWidget):
    """
    Fixed action stack for WorkspacePage right rail.

      [ Open  ] [ Reset    ]
      [ Save  ] [ Retouch  ]   (shown only when a result is ready)
      [ Enhance ]              (shown only when a result is ready)
      [ Compare ]              (Video tab — side-by-side original|cleaned)
      [ Processing N% + bar ]  (shown while running, when progress_label set)
      [       Run/Stop     ]
    """

    open_clicked = Signal()
    run_clicked = Signal()
    stop_confirmed = Signal()
    save_clicked = Signal()
    retouch_clicked = Signal()
    enhance_clicked = Signal()
    compare_clicked = Signal()
    reset_confirmed = Signal()

    def __init__(self, actions: RailActions, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionBar")
        self.setBorderRadius(SECTION["radius"])
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._stop_confirm_title = actions.stop_confirm_title
        self._stop_confirm_desc = actions.stop_confirm_desc
        self._reset_confirm_title = actions.reset_confirm_title
        self._reset_confirm_desc = actions.reset_confirm_desc
        self._has_save = bool(actions.save_text)
        self._has_retouch = bool(actions.retouch_text)
        self._has_enhance = bool(actions.enhance_text)
        self._has_compare = bool(actions.compare_text)
        self._has_reset = bool(actions.reset_text)
        self._progress_fmt = actions.progress_label or ""
        self._has_progress = bool(self._progress_fmt)
        self._throttle = ClickThrottle(_CLICK_THROTTLE_MS)

        root = QVBoxLayout(self)
        root.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        root.setSpacing(_GAP)

        # Row 0 - Open | Reset
        row0 = QHBoxLayout()
        row0.setContentsMargins(0, 0, 0, 0)
        row0.setSpacing(_GAP)

        self.open_button = make_button(actions.open_text, "secondary", self, FluentIcon.FOLDER)
        self.open_button.clicked.connect(lambda: self._emit_throttled(self.open_clicked))
        self._style_btn(self.open_button)
        row0.addWidget(self.open_button, 1)

        self.reset_button = make_button(
            actions.reset_text or "Reset", "secondary", self, FluentIcon.DELETE
        )
        self.reset_button.clicked.connect(self._on_reset_clicked)
        self.reset_button.setVisible(self._has_reset)
        self._style_btn(self.reset_button)
        row0.addWidget(self.reset_button, 1)
        root.addLayout(row0)

        # Row 1 - Save | Retouch (whole row hidden on Video tab)
        self._mid_row = QWidget(self)
        mid = QHBoxLayout(self._mid_row)
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(_GAP)

        self.save_button = make_button(
            actions.save_text or "Save", "secondary", self, FluentIcon.SAVE
        )
        self.save_button.clicked.connect(lambda: self._emit_throttled(self.save_clicked))
        self.save_button.setEnabled(False)
        self.save_button.setVisible(False)
        self._style_btn(self.save_button)
        mid.addWidget(self.save_button, 1)

        self.retouch_button = make_button(
            actions.retouch_text or "Retouch", "warning", self, FluentIcon.EDIT
        )
        self.retouch_button.clicked.connect(lambda: self._emit_throttled(self.retouch_clicked))
        self.retouch_button.setEnabled(False)
        self.retouch_button.setVisible(False)
        self._style_btn(self.retouch_button)
        mid.addWidget(self.retouch_button, 1)

        self._mid_row.setVisible(False)
        root.addWidget(self._mid_row)

        # Row 1b - Enhance (Remove BG only; shown after result is ready)
        self.enhance_button = make_button(
            actions.enhance_text or "Enhance", "danger", self, FluentIcon.ZOOM
        )
        self.enhance_button.clicked.connect(lambda: self._emit_throttled(self.enhance_clicked))
        self.enhance_button.setEnabled(False)
        self.enhance_button.setVisible(False)
        self._style_btn(self.enhance_button)
        root.addWidget(self.enhance_button)

        # Compare (Video tab — side-by-side original | cleaned)
        self.compare_button = make_button(
            actions.compare_text or "Compare", "secondary", self, FluentIcon.ALIGNMENT
        )
        self.compare_button.clicked.connect(lambda: self._emit_throttled(self.compare_clicked))
        self.compare_button.setEnabled(False)
        self.compare_button.setVisible(False)
        self._style_btn(self.compare_button)
        root.addWidget(self.compare_button)

        # Progress (optional) - same chrome as enhance / retouch dialogs
        self.progress_panel = QWidget(self)
        prog = QVBoxLayout(self.progress_panel)
        prog.setContentsMargins(0, 0, 0, 0)
        prog.setSpacing(FORM["tight_spacing"])
        self.progress_label = BodyLabel(
            self._progress_fmt.format(0) if self._has_progress else "",
            self.progress_panel,
        )
        self.progress_label.setStyleSheet(
            f"color: {TEXT}; background: transparent; border: none;"
        )
        prog.addWidget(self.progress_label)
        self.progress_bar = ProgressBar(self.progress_panel)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        prog.addWidget(self.progress_bar)
        self.progress_panel.setVisible(False)
        root.addWidget(self.progress_panel)

        # Row 2 - Run / Stop (full width, one visible at a time)
        self._run_row = QWidget(self)
        run_row = QHBoxLayout(self._run_row)
        run_row.setContentsMargins(0, 0, 0, 0)
        run_row.setSpacing(0)

        self.run_button = make_button(actions.run_text, "primary", self, FluentIcon.PLAY)
        self.run_button.clicked.connect(lambda: self._emit_throttled(self.run_clicked))
        self._style_btn(self.run_button)
        run_row.addWidget(self.run_button, 1)

        self.stop_button = make_stop_button(actions.stop_text, self)
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self._style_btn(self.stop_button)
        run_row.addWidget(self.stop_button, 1)

        root.addWidget(self._run_row)
        self.setMinimumHeight(WORKSPACE["action_bar_min_h"])

    def _emit_throttled(self, signal: Signal):
        if self._throttle.allow():
            signal.emit()

    @staticmethod
    def _style_btn(btn):
        btn.setFixedHeight(_BTN_H)
        btn.setIconSize(QSize(_BTN_ICON, _BTN_ICON))
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _normalBackgroundColor(self):
        return QColor(SECTION["bg"])

    def _hoverBackgroundColor(self):
        return self._normalBackgroundColor()

    def _pressedBackgroundColor(self):
        return self._normalBackgroundColor()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.backgroundColor)
        painter.setPen(QColor(SECTION["border"]))
        r = self.borderRadius
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), r, r)

    def _on_stop_clicked(self):
        if not self._throttle.allow():
            return
        if ask_confirm(self._stop_confirm_title, self._stop_confirm_desc, self.window()):
            self.stop_confirmed.emit()

    def _on_reset_clicked(self):
        if not self._throttle.allow():
            return
        if ask_confirm(self._reset_confirm_title, self._reset_confirm_desc, self.window()):
            self.reset_confirmed.emit()

    def set_running(self, running: bool):
        was_running = self.stop_button.isVisible()
        self.run_button.setVisible(not running)
        self.stop_button.setVisible(running)
        idle = not running
        self.reset_button.setVisible(idle and self._has_reset)
        self._sync_result_actions(idle=idle)
        if self._has_progress:
            if running and not was_running:
                self.set_progress(0)
            elif not running:
                self.hide_progress()

    def set_progress(self, value: int):
        """Show ``Processing N%`` in the action rail (0–100)."""
        if not self._has_progress:
            return
        pct = max(0, min(100, int(value)))
        self.progress_bar.setValue(pct)
        self.progress_label.setText(self._progress_fmt.format(pct))
        self.progress_panel.setVisible(True)

    def hide_progress(self):
        if not self._has_progress:
            return
        self.progress_panel.setVisible(False)
        self.progress_bar.setValue(0)

    def _sync_result_actions(self, *, idle: bool | None = None):
        """Show Save / Retouch / Enhance only when enabled and not running."""
        if idle is None:
            idle = not self.stop_button.isVisible()
        show_save = idle and self._has_save and self.save_button.isEnabled()
        show_retouch = idle and self._has_retouch and self.retouch_button.isEnabled()
        show_enhance = idle and self._has_enhance and self.enhance_button.isEnabled()
        show_compare = idle and self._has_compare and self.compare_button.isEnabled()
        self.save_button.setVisible(show_save)
        self.retouch_button.setVisible(show_retouch)
        self._mid_row.setVisible(show_save or show_retouch)
        self.enhance_button.setVisible(show_enhance)
        self.compare_button.setVisible(show_compare)

    def set_open_enabled(self, enabled: bool):
        self.open_button.setEnabled(enabled)

    def set_run_enabled(self, enabled: bool):
        self.run_button.setEnabled(enabled)

    def set_save_enabled(self, enabled: bool):
        self.save_button.setEnabled(enabled)
        self._sync_result_actions()

    def set_retouch_enabled(self, enabled: bool):
        self.retouch_button.setEnabled(enabled)
        self._sync_result_actions()

    def set_enhance_enabled(self, enabled: bool):
        self.enhance_button.setEnabled(enabled)
        self._sync_result_actions()

    def set_compare_enabled(self, enabled: bool):
        self.compare_button.setEnabled(enabled)
        self._sync_result_actions()

    def set_reset_enabled(self, enabled: bool):
        self.reset_button.setEnabled(enabled)
