"""Midgard setting row card - plain QFrame chrome from ``ui.theme.CARD``"""

from __future__ import annotations

from typing import Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import FluentIconBase, Theme

from ui.component.cards.setting_card_style import (
    apply_settings_card,
    compact_setting_card,
    settings_content_summary,
)
from ui.theme import CARD


def _to_pixmap(icon: Union[str, QIcon, FluentIconBase, None], size: int) -> QPixmap:
    if icon is None:
        return QPixmap()
    if isinstance(icon, FluentIconBase):
        return icon.icon(Theme.DARK).pixmap(size, size)
    if isinstance(icon, QIcon):
        return icon.pixmap(size, size)
    if isinstance(icon, str):
        return QIcon(icon).pixmap(size, size)
    return QPixmap()


class MidgardSettingCard(QFrame):
    """Row card: icon + title/content + trailing controls. Theme-only chrome."""

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase, None],
        title: str,
        content: str = "",
        parent: QWidget | None = None,
        *,
        detailed: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("MidgardSettingCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        c = CARD
        self.iconLabel = QLabel(self)
        self.iconLabel.setObjectName("iconLabel")
        self.iconLabel.setFixedSize(c["icon"], c["icon"])
        pix = _to_pixmap(icon, c["icon"])
        if not pix.isNull():
            self.iconLabel.setPixmap(pix)

        self.titleLabel = QLabel(title, self)
        self.titleLabel.setObjectName("titleLabel")
        self.contentLabel = QLabel(content or "", self)
        self.contentLabel.setObjectName("contentLabel")
        self._detailed = detailed
        if content:
            self._apply_content_text(content)
        else:
            self.contentLabel.hide()

        self.hBoxLayout = QHBoxLayout(self)
        self.vBoxLayout = QVBoxLayout()

        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.hBoxLayout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignLeft)
        self.hBoxLayout.addSpacing(c["icon_gap"])
        self.hBoxLayout.addLayout(self.vBoxLayout, 1)
        self.vBoxLayout.addWidget(self.titleLabel, 0, Qt.AlignmentFlag.AlignLeft)
        self.vBoxLayout.addWidget(self.contentLabel, 0, Qt.AlignmentFlag.AlignLeft)
        self.hBoxLayout.addStretch(1)

        if detailed:
            apply_settings_card(self)
        else:
            compact_setting_card(self)

    def _apply_content_text(self, content: str):
        full = content or ""
        if self._detailed and full:
            self.contentLabel.setToolTip(full)
            display = settings_content_summary(full)
        else:
            self.contentLabel.setToolTip("")
            display = full
        self.contentLabel.setText(display)
        self.contentLabel.setVisible(bool(display))

    def setTitle(self, title: str):
        self.titleLabel.setText(title)

    def setContent(self, content: str):
        self._apply_content_text(content or "")

    def setValue(self, value):
        pass

    def setIconSize(self, width: int, height: int):
        self.iconLabel.setFixedSize(width, height)
