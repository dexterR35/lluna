"""Editor shell - same visual rail as WorkspacePage (preview + right SectionCards).

Used by modal editors (Retouch) that need canvas + tools without Tasks/ActionBar.
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLayout, QSizePolicy, QVBoxLayout, QWidget

from backend.config import config
from ui.component.workspace.workspace_page import SectionCard
from ui.theme import PAGE, WORKSPACE


def present_editor_dialog(dialog: QDialog, image_size: Tuple[int, int] | None = None) -> str:
    """
    Show an editor dialog at the fixed config size (never auto-maximize).

    Canvas keeps native image pixels and zoom-fits inside the viewport.
    ``image_size`` is unused for layout (kept for call-site compatibility).

    Returns ``"normal"`` for diagnostics.
    """
    _ = image_size  # canvas zoom handles large images; window stays fixed

    scr = None
    parent = dialog.parentWidget()
    if parent is not None and parent.screen() is not None:
        scr = parent.screen()
    elif dialog.screen() is not None:
        scr = dialog.screen()
    else:
        scr = QGuiApplication.primaryScreen()

    tw = int(config.retouchWindowW)
    th = int(config.retouchWindowH)
    if scr is not None:
        screen = scr.availableGeometry()
        # Stay within ~90% of the screen on small displays
        tw = min(tw, max(800, int(screen.width() * 0.90)))
        th = min(th, max(560, int(screen.height() * 0.90)))
    else:
        screen = None

    # Clear any inherited maximized state from the parent main window
    dialog.setWindowState(Qt.WindowState.WindowNoState)
    dialog.resize(tw, th)
    if screen is not None:
        dialog.move(
            screen.x() + max(0, (screen.width() - tw) // 2),
            screen.y() + max(0, (screen.height() - th) // 2),
        )
    dialog.showNormal()
    return "normal"


class EditorPage(QWidget):
    """
    [ Preview SectionCard (stretch) ] [ Right rail - SectionCards + footer ]

    Rail width matches WorkspacePage (``WORKSPACE["rail_width"]``).
    """

    def __init__(
        self,
        preview: Union[QWidget, QLayout],
        parent=None,
        *,
        preview_title: Optional[str] = None,
        preview_bordered: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("EditorPage")

        root = QHBoxLayout(self)
        root.setSpacing(0)
        m = PAGE["margin"]
        root.setContentsMargins(m, m, m, m)

        left = QVBoxLayout()
        left.setSpacing(PAGE["column_spacing"])
        left.setContentsMargins(0, 0, PAGE["spacing"], 0)

        self.preview_section = SectionCard(
            self,
            title=preview_title,
            bordered=preview_bordered,
        )
        self.preview_section.set_content(preview)
        left.addWidget(self.preview_section, 1)
        root.addLayout(left, 1)

        self.right_rail = QWidget(self)
        self.right_rail.setObjectName("WorkspaceRightRail")
        self.right_rail.setFixedWidth(WORKSPACE["rail_width"])
        self.right_rail.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self.rail_layout = QVBoxLayout(self.right_rail)
        self.rail_layout.setContentsMargins(PAGE["spacing"], 0, 0, 0)
        self.rail_layout.setSpacing(WORKSPACE["rail_spacing"])
        root.addWidget(self.right_rail, 0)

    def add_section(
        self,
        title: str,
        content: Union[QWidget, QLayout],
        *,
        stretch: int = 0,
        compact_title: bool = True,
    ) -> SectionCard:
        """Append a titled SectionCard to the right rail."""
        card = SectionCard(
            self.right_rail, title=title, compact_title=compact_title
        )
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.set_content(content)
        self.rail_layout.addWidget(card, stretch)
        return card

    def add_rail_widget(self, widget: QWidget, stretch: int = 0):
        self.rail_layout.addWidget(widget, stretch)

    def add_rail_stretch(self, stretch: int = 1):
        self.rail_layout.addStretch(stretch)
