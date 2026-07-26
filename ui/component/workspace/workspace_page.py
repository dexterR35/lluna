"""Shared workspace layout for Video and Remove BG tools.

  ┌ preview (large) ────────┬─ settings ─┐
  │                         │  tasks       │
  ├─────────────────────────┴──────────────┤
  │  log                                   │
  └────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import Optional, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, SubtitleLabel
from backend.config import tr
from ui.component.workspace.action_bar import ActionBar, RailActions
from ui.component.workspace.log_panel import LogPanel
from ui.component.workspace.task_list_component import TaskListComponent
from ui.theme import PAGE, SECTION, WORKSPACE


class SectionCard(CardWidget):
    """Soft rounded pane used for preview, settings, and tasks.

    ``bordered=False`` is a transparent layout host (no fill / no border) so
    child panes (e.g. Before / After) can show their own borders clearly.
    Look comes from ``theme.SECTION``.
    """

    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        bordered: bool = True,
        compact_title: bool = False,
    ):
        # Must set before super() - CardWidget reads background color during init
        self._bordered = bordered
        self._compact_title = compact_title
        super().__init__(parent)
        self.setObjectName("SectionCard")
        s = SECTION
        self.setBorderRadius(s["radius"])
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if not bordered:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._root = QVBoxLayout(self)
        pad = s["rail_pad"] if compact_title else s["pad"]
        if bordered:
            self._root.setContentsMargins(pad, pad, pad, pad)
        elif title:
            self._root.setContentsMargins(pad, pad // 2, pad, 0)
        else:
            self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(s["spacing"])

        self.title_label: Optional[SubtitleLabel] = None
        if title:
            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            self.title_label = SubtitleLabel(title, self)
            self.title_label.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
            )
            font = QFont(self.title_label.font())
            if compact_title:
                font.setPointSize(s["rail_title_size"])
                font.setWeight(QFont.Weight.Medium)
                title_color = s["rail_title_color"]
            else:
                font.setPointSize(s["title_size"])
                title_color = s["title"]
            self.title_label.setFont(font)
            self.title_label.setStyleSheet(
                f"color: {title_color}; background: transparent; border: none;"
            )
            title_row.addWidget(self.title_label, 0)
            title_row.addStretch(1)
            self._root.addLayout(title_row)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(s["spacing"])
        self._root.addLayout(self.body, 1)

    def _normalBackgroundColor(self):
        if not self._bordered:
            return QColor(0, 0, 0, 0)
        return QColor(SECTION["bg"])

    def _hoverBackgroundColor(self):
        return self._normalBackgroundColor()

    def _pressedBackgroundColor(self):
        return self._normalBackgroundColor()

    def paintEvent(self, e):
        if not self._bordered:
            return
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.backgroundColor)
        painter.setPen(QColor(SECTION["border"]))
        r = self.borderRadius
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), r, r)

    def set_content(self, content: Union[QWidget, QLayout]):
        """Place a widget or layout into the section body."""
        if isinstance(content, QLayout):
            self.body.addLayout(content, 1)
        else:
            self.body.addWidget(content, 1)


class WorkspacePage(QWidget):
    """
    Shared ChatGPT-style rounded layout for Video and Remove BG tools.

    Left:  preview section (stretch) + log
    Right: side rail - settings + task list + ActionBar
    """

    def __init__(
        self,
        preview: Union[QWidget, QLayout],
        settings: Union[QWidget, QLayout],
        actions: RailActions,
        parent=None,
        *,
        preview_title: Optional[str] = None,
        preview_bordered: bool = True,
        tasks_title: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setObjectName("WorkspacePage")

        root = QHBoxLayout(self)
        root.setSpacing(0)
        m = PAGE["margin"]
        root.setContentsMargins(m, m, m, m)

        # --- Left: preview + log ---
        left = QVBoxLayout()
        left.setSpacing(PAGE["column_spacing"])
        left.setContentsMargins(0, 0, PAGE["spacing"], 0)

        self.preview_section = SectionCard(
            self,
            title=preview_title or tr["SubtitleExtractorGUI"].get("VideoPreview", "Preview"),
            bordered=preview_bordered,
        )
        self.preview_section.set_content(preview)
        left.addWidget(self.preview_section, WORKSPACE["preview_stretch"])

        self.log_section = SectionCard(
            self,
            title=tr["SubtitleExtractorGUI"].get("Log", "Log"),
        )
        # Compact chrome so the log text isn't squeezed under the title
        pad = SECTION["pad"]
        self.log_section._root.setContentsMargins(pad, pad // 2, pad, pad // 2)
        self.log_section._root.setSpacing(max(4, SECTION["spacing"] // 2))
        self.log_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.log_panel = LogPanel(self, minimum_height=WORKSPACE["log_min_h"])
        self.log_section.set_content(self.log_panel)
        self.log_section.setFixedHeight(WORKSPACE["log_max_h"])
        left.addWidget(self.log_section, WORKSPACE["log_stretch"])
        root.addLayout(left, 1)

        # --- Right rail ---
        self.right_rail = QWidget(self)
        self.right_rail.setObjectName("WorkspaceRightRail")
        self.right_rail.setFixedWidth(WORKSPACE["rail_width"])
        self.right_rail.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        right = QVBoxLayout(self.right_rail)
        right.setContentsMargins(PAGE["spacing"], 0, 0, 0)
        right.setSpacing(WORKSPACE["rail_spacing"])

        settings_title = actions.settings_title or tr["SubtitleExtractorGUI"].get(
            "Setting", "Settings"
        )
        self.settings_section = SectionCard(self.right_rail, title=settings_title)
        self.settings_section.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self.settings_section.set_content(settings)
        right.addWidget(self.settings_section, 0)

        task_label = tasks_title or tr["TaskList"].get("Title", "Tasks")
        self.task_section = SectionCard(self.right_rail, title=task_label)
        self.task_list_component = TaskListComponent(self)
        if actions.empty_list_hint:
            self.task_list_component.empty_hint.setText(actions.empty_list_hint)
        self.task_section.set_content(self.task_list_component)
        right.addWidget(self.task_section, WORKSPACE["task_stretch"])

        self.action_bar = ActionBar(actions, parent=self.right_rail)
        right.addWidget(self.action_bar, 0)

        root.addWidget(self.right_rail, 0)
