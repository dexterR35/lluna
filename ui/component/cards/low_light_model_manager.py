"""Low Light (MIRNet) models as SettingCards - same pattern as Enhance models."""

from __future__ import annotations

import threading
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from qfluentwidgets import FluentIcon, SwitchButton
from qfluentwidgets.components.widgets.switch_button import IndicatorPosition

from backend.config import tr
from backend.tools.constant import LowLightMode
from backend.tools.low_light_models import (
    MODEL_CATALOG,
    LowLightModelInfo,
    get_enabled_values,
    install_model,
    is_model_installed,
    set_model_enabled,
    uninstall_model,
)
from ui.component.cards.midgard_card import MidgardSettingCard
from ui.component.controls.button_styles import make_button
from ui.component.utils.confirm_dialog import ask_confirm
from ui.theme import CARD


class LowLightModelCard(MidgardSettingCard):
    install_requested = Signal(object)
    uninstall_requested = Signal(object)
    enabled_changed = Signal()

    def __init__(self, info: LowLightModelInfo, parent=None):
        title = tr["LowLightMode"].get(info.mode.name, info.mode.name)
        content = tr["LowLightModelDesc"].get(info.desc_key, "")
        super().__init__(FluentIcon.BRIGHTNESS, title, content, parent, detailed=True)
        self.info = info
        self._busy = False

        off = tr["LowLight"].get("ToggleOff", tr["BgRemove"]["ToggleOff"])
        on = tr["LowLight"].get("ToggleOn", tr["BgRemove"]["ToggleOn"])
        self.switchButton = SwitchButton(off, self, IndicatorPosition.RIGHT)
        self.switchButton.setOnText(on)
        self.switchButton.setOffText(off)
        self.switchButton.checkedChanged.connect(self._on_switch)
        gap = CARD["trailing_gap"]
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.uninstallButton = make_button(
            tr["LowLight"].get(
                "ActionUninstall", tr["BgRemove"].get("ActionUninstall", "Uninstall")
            ),
            "secondary",
            self,
            FluentIcon.DELETE,
        )
        self.uninstallButton.clicked.connect(
            lambda: self.uninstall_requested.emit(self.info.mode)
        )
        self.hBoxLayout.addWidget(self.uninstallButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.installButton = make_button(
            tr["LowLight"].get("ActionInstall", tr["BgRemove"]["ActionInstall"]),
            "primary",
            self,
            FluentIcon.DOWNLOAD,
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
        self.uninstallButton.setEnabled(enabled and installed)
        self.switchButton.setEnabled(enabled and installed)

    def refresh(self):
        ll = tr["LowLight"]
        br = tr["BgRemove"]
        installed = is_model_installed(self.info.mode)
        enabled = self.info.mode.value in get_enabled_values()
        desc = tr["LowLightModelDesc"].get(self.info.desc_key, "")

        if installed:
            suffix = ll.get("StatusInstalled", br["StatusInstalled"])
            if self.info.is_default:
                suffix = f"{suffix} · {ll.get('StatusDefault', br['StatusDefault'])}"
            self.setContent(f"{desc} ({suffix})" if desc else suffix)
            self.installButton.hide()
            self.uninstallButton.show()
            self.uninstallButton.setEnabled(not self._busy)
            self.switchButton.show()
            self.switchButton.blockSignals(True)
            self.switchButton.setChecked(enabled)
            self.switchButton.blockSignals(False)
            self.switchButton.setEnabled(not self._busy)
        else:
            self.setContent(desc)
            self.switchButton.hide()
            self.uninstallButton.hide()
            self.installButton.show()
            self.installButton.setEnabled(not self._busy)
            self.installButton.setText(ll.get("ActionInstall", br["ActionInstall"]))


class LowLightModelManager(QObject):
    models_changed = Signal()
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._installing = False
        self._processing = False
        self.cards: List[LowLightModelCard] = []

        for info in MODEL_CATALOG:
            card = LowLightModelCard(info, parent)
            card.install_requested.connect(self._start_install)
            card.uninstall_requested.connect(self._start_uninstall)
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
        ll = tr["LowLight"]
        br = tr["BgRemove"]
        locked = self._installing or self._processing
        for card in self.cards:
            card.set_controls_enabled(not locked)
            if self._installing and card.installButton.isVisible():
                card.installButton.setText(
                    ll.get("ActionInstalling", br["ActionInstalling"])
                )
            elif card.installButton.isVisible():
                card.installButton.setText(
                    ll.get("ActionInstall", br["ActionInstall"])
                )
            if self._installing and card.uninstallButton.isVisible():
                card.uninstallButton.setText(
                    ll.get(
                        "ActionUninstalling",
                        br.get("ActionUninstalling", "Removing…"),
                    )
                )
            elif card.uninstallButton.isVisible():
                card.uninstallButton.setText(
                    ll.get(
                        "ActionUninstall",
                        br.get("ActionUninstall", "Uninstall"),
                    )
                )

    def restart_install(self, mode: LowLightMode):
        """Start over an aborted download (no resume)."""
        if is_model_installed(mode):
            from backend.tools.model_download_registry import (
                KIND_LOW_LIGHT,
                ModelDownloadRegistry,
            )

            ModelDownloadRegistry.instance().complete(KIND_LOW_LIGHT, mode.value)
            self.refresh()
            return
        if self._installing or self._processing:
            QTimer.singleShot(1500, lambda m=mode: self.restart_install(m))
            return
        self._start_install(mode)

    def _start_install(self, mode: LowLightMode):
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

    def _finish_install(self, mode: LowLightMode, err: Optional[BaseException]):
        from backend.tools.model_download_registry import DownloadCancelled

        self._installing = False
        if err is None:
            set_model_enabled(mode, True)
            from backend.config import config

            config.set(config.lowLightMode, mode)
        self.refresh()
        self.busy_changed.emit(False)
        if isinstance(err, DownloadCancelled):
            return
        ll = tr["LowLight"]
        br = tr["BgRemove"]
        name = tr["LowLightMode"].get(mode.name, mode.value)
        if err:
            self.status_message.emit(
                ll.get("InstallFailed", br["InstallFailed"]).format(str(err))
            )
        else:
            self.status_message.emit(
                ll.get("InstallDone", br["InstallDone"]).format(name)
            )

    def _start_uninstall(self, mode: LowLightMode):
        if self._installing or self._processing:
            return
        ll = tr["LowLight"]
        br = tr["BgRemove"]
        name = tr["LowLightMode"].get(mode.name, mode.value)
        parent = self.cards[0].window() if self.cards else None
        if not ask_confirm(
            ll.get(
                "UninstallConfirmTitle",
                br.get("UninstallConfirmTitle", "Uninstall model?"),
            ),
            ll.get(
                "UninstallConfirmDesc",
                br.get(
                    "UninstallConfirmDesc",
                    "Delete local files for {}? You can install it again later.",
                ),
            ).format(name),
            parent,
        ):
            return
        self._installing = True
        self._apply_lock()
        self.busy_changed.emit(True)

        def work():
            err = None
            try:
                uninstall_model(mode)
            except Exception as e:
                err = e
            QTimer.singleShot(0, lambda: self._finish_uninstall(mode, err))

        threading.Thread(target=work, daemon=True).start()

    def _finish_uninstall(self, mode: LowLightMode, err: Optional[BaseException]):
        self._installing = False
        self.refresh()
        self.busy_changed.emit(False)
        ll = tr["LowLight"]
        br = tr["BgRemove"]
        name = tr["LowLightMode"].get(mode.name, mode.value)
        if err:
            self.status_message.emit(
                ll.get(
                    "UninstallFailed",
                    br.get("UninstallFailed", "Uninstall failed: {}"),
                ).format(str(err))
            )
        else:
            self.status_message.emit(
                ll.get(
                    "UninstallDone",
                    br.get("UninstallDone", "Uninstalled: {}"),
                ).format(name)
            )
