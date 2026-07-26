"""Home / info row card — Midgard theme chrome (no Fluent SettingCard)."""

from __future__ import annotations

from typing import Union

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import FluentIconBase

from ui.component.cards.midgard_card import MidgardSettingCard


class InfoSettingCard(MidgardSettingCard):
    """Compact info row for Home dashboard chips."""

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase],
        title: str,
        content: str = "",
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self.setObjectName("InfoSettingCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
