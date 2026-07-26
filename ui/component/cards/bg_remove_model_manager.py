"""Remove BG models as native SettingCards (same design as STTN / ProPainter)."""

from __future__ import annotations

import threading
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from qfluentwidgets import FluentIcon, SwitchButton
from qfluentwidgets.components.widgets.switch_button import IndicatorPosition

from backend.config import tr
from backend.tools.bg_remove_models import (
    MODEL_CATALOG,
    BgRemoveModelInfo,
    get_enabled_values,
    install_model,
    is_model_installed,
    set_model_enabled,
)
from backend.tools.constant import BgRemoveMode
from ui.component.cards.midgard_card import MidgardSettingCard
from ui.component.controls.button_styles import make_button
from ui.theme import CARD


def _model_icon(info: BgRemoveModelInfo):
    if info.category == "People":
        return FluentIcon.PEOPLE
    if info.category == "Anime":
        return FluentIcon.PHOTO
    if info.category == "Clothes":
        return FluentIcon.SHOPPING_CART
    if info.category == "Specialty":
        return FluentIcon.SEARCH
    return FluentIcon.PHOTO


class BgRemoveModelCard(MidgardSettingCard):
    """One rembg model - Install when missing; On/Off when installed."""

    install_requested = Signal(object)
    enabled_changed = Signal()

    def __init__(self, info: BgRemoveModelInfo, parent=None):
        title = tr["BgRemoveMode"].get(info.mode.name, info.mode.name)
        content = tr["BgRemoveModelDesc"].get(info.desc_key, "")
        super().__init__(_model_icon(info), title, content, parent, detailed=True)
        self.info = info
        self._busy = False

        self.switchButton = SwitchButton(
            tr["BgRemove"]["ToggleOff"], self, IndicatorPosition.RIGHT
        )
        self.switchButton.setOnText(tr["BgRemove"]["ToggleOn"])
        self.switchButton.setOffText(tr["BgRemove"]["ToggleOff"])
        self.switchButton.checkedChanged.connect(self._on_switch)
        gap = CARD["trailing_gap"]
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.installButton = make_button(
            tr["BgRemove"]["ActionInstall"], "primary", self, FluentIcon.DOWNLOAD
        )
        self.installButton.clicked.connect(
            lambda: self.install_requested.emit(self.info.mode)
        )
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.refresh()

    def _on_switch(self, checked: bool):
        if self._busy:
            return
        set_model_enabled(self.info.mode, checked)
        self.enabled_changed.emit()
        self.refresh()

    def set_controls_enabled(self, enabled: bool):
        self._busy = not enabled
        installed = is_model_installed(self.info.mode)
        self.installButton.setEnabled(enabled and not installed)
        self.switchButton.setEnabled(enabled and installed)

    def refresh(self):
        installed = is_model_installed(self.info.mode)
        enabled = self.info.mode.value in get_enabled_values()
        desc = tr["BgRemoveModelDesc"].get(self.info.desc_key, "")

        if installed:
            suffix = tr["BgRemove"]["StatusInstalled"]
            if self.info.is_default:
                suffix = f"{suffix} · {tr['BgRemove']['StatusDefault']}"
            self.setContent(f"{desc} ({suffix})" if desc else suffix)
            self.installButton.hide()
            self.switchButton.show()
            self.switchButton.blockSignals(True)
            self.switchButton.setChecked(enabled)
            self.switchButton.blockSignals(False)
            self.switchButton.setEnabled(not self._busy)
        else:
            self.setContent(desc)
            self.switchButton.hide()
            self.installButton.show()
            self.installButton.setEnabled(not self._busy)
            self.installButton.setText(tr["BgRemove"]["ActionInstall"])


class BgRemoveModelManager(QObject):
    """Owns model SettingCards and install / refresh logic (not a custom panel)."""

    models_changed = Signal()
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._installing = False
        self._processing = False
        self.cards: List[BgRemoveModelCard] = []

        for info in MODEL_CATALOG:
            card = BgRemoveModelCard(info, parent)
            card.install_requested.connect(self._start_install)
            card.enabled_changed.connect(self.models_changed.emit)
            self.cards.append(card)

        self.refresh()

    @property
    def is_busy(self) -> bool:
        return self._installing

    def set_processing(self, processing: bool):
        self._processing = processing
        self._apply_lock()

    def refresh(self):
        for card in self.cards:
            card.refresh()
        self._apply_lock()
        self.models_changed.emit()

    def _apply_lock(self):
        locked = self._installing or self._processing
        for card in self.cards:
            card.set_controls_enabled(not locked)
            if self._installing and card.installButton.isVisible():
                card.installButton.setText(tr["BgRemove"]["ActionInstalling"])
            elif card.installButton.isVisible():
                card.installButton.setText(tr["BgRemove"]["ActionInstall"])

    def _start_install(self, mode: BgRemoveMode):
        if self._installing or self._processing:
            return
        self._installing = True
        self._apply_lock()
        self.busy_changed.emit(True)

        def work():
            err = None
            try:
                install_model(mode)
            except Exception as e:
                err = e
            QTimer.singleShot(0, lambda: self._finish_install(mode, err))

        threading.Thread(target=work, daemon=True).start()

    def _finish_install(self, mode: BgRemoveMode, err: Optional[BaseException]):
        self._installing = False
        self.refresh()
        self.busy_changed.emit(False)
        name = tr["BgRemoveMode"].get(mode.name, mode.value)
        if err:
            self.status_message.emit(tr["BgRemove"]["InstallFailed"].format(str(err)))
        else:
            self.status_message.emit(tr["BgRemove"]["InstallDone"].format(name))
