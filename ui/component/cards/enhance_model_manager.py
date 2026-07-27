"""Upscale (Real-ESRGAN) models as SettingCards - same pattern as Remove BG models."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, Qt, Signal
from qfluentwidgets import FluentIcon, SwitchButton
from qfluentwidgets.components.widgets.switch_button import IndicatorPosition

from backend.config import tr
from backend.tools.constant import EnhanceMode
from backend.tools.enhance_models import (
    MODEL_CATALOG,
    EnhanceModelInfo,
    get_enabled_values,
    install_model,
    is_model_installed,
    set_model_enabled,
    uninstall_model,
)
from backend.tools.model_download_registry import KIND_ENHANCE
from ui.component.cards.midgard_card import MidgardSettingCard
from ui.component.cards.model_install_helpers import (
    enqueue_model_job,
    install_button_text,
    job_state,
    register_queue_listener,
)
from ui.component.controls.button_styles import make_button
from ui.component.utils.confirm_dialog import ask_confirm
from ui.theme import CARD


class EnhanceModelCard(MidgardSettingCard):
    install_requested = Signal(object)
    uninstall_requested = Signal(object)
    enabled_changed = Signal()

    def __init__(self, info: EnhanceModelInfo, parent=None):
        title = tr["EnhanceMode"].get(info.mode.name, info.mode.name)
        content = tr["EnhanceModelDesc"].get(info.desc_key, "")
        super().__init__(FluentIcon.ZOOM, title, content, parent, detailed=True)
        self.info = info
        self._busy = False

        off = tr["Upscale"].get("ToggleOff", "Off")
        on = tr["Upscale"].get("ToggleOn", "On")
        self.switchButton = SwitchButton(off, self, IndicatorPosition.RIGHT)
        self.switchButton.setOnText(on)
        self.switchButton.setOffText(off)
        self.switchButton.checkedChanged.connect(self._on_switch)
        gap = CARD["trailing_gap"]
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.uninstallButton = make_button(
            tr["Upscale"].get("ActionUninstall", "Uninstall"),
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
            tr["Upscale"]["ActionInstall"],
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
        key = self.info.mode.value
        queued = job_state(KIND_ENHANCE, key) is not None
        self.installButton.setEnabled(enabled and not installed and not queued)
        self.uninstallButton.setEnabled(enabled and installed and not queued)
        self.switchButton.setEnabled(enabled and installed and not queued)

    def refresh(self):
        up = tr["Upscale"]
        installed = is_model_installed(self.info.mode)
        enabled = self.info.mode.value in get_enabled_values()
        desc = tr["EnhanceModelDesc"].get(self.info.desc_key, "")

        if installed:
            suffix = up["StatusInstalled"]
            if self.info.is_default:
                suffix = f"{suffix} · {up['StatusDefault']}"
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
            self.installButton.setText(up["ActionInstall"])


class EnhanceModelManager(QObject):
    models_changed = Signal()
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._processing = False
        self._was_busy = False
        self.cards: List[EnhanceModelCard] = []

        for info in MODEL_CATALOG:
            card = EnhanceModelCard(info, parent)
            card.install_requested.connect(self._start_install)
            card.uninstall_requested.connect(self._start_uninstall)
            card.enabled_changed.connect(self.models_changed.emit)
            self.cards.append(card)

        register_queue_listener(self._on_queue_changed)
        self.refresh()

    @property
    def is_busy(self) -> bool:
        return self._has_queue_activity()

    def set_processing(self, processing: bool):
        self._processing = processing
        self._apply_lock()

    def refresh(self):
        for card in self.cards:
            card.refresh()
        self._apply_lock()
        self.models_changed.emit()

    def _has_queue_activity(self) -> bool:
        for card in self.cards:
            if job_state(KIND_ENHANCE, card.info.mode.value):
                return True
        return False

    def _on_queue_changed(self):
        busy = self._has_queue_activity()
        if busy != self._was_busy:
            self._was_busy = busy
            self.busy_changed.emit(busy)
        self._apply_lock()

    def _apply_lock(self):
        up = tr["Upscale"]
        set_tr = tr["Setting"]
        locked = self._has_queue_activity() or self._processing
        queued_fmt = set_tr.get("ActionQueued", "Queued ({})")
        for card in self.cards:
            card.set_controls_enabled(not locked)
            key = card.info.mode.value
            state = job_state(KIND_ENHANCE, key)
            if card.installButton.isVisible():
                card.installButton.setText(
                    install_button_text(
                        kind=KIND_ENHANCE,
                        key=key,
                        installing_text=up["ActionInstalling"],
                        queued_text=queued_fmt,
                        install_text=up["ActionInstall"],
                    )
                )
                if state:
                    card.installButton.setEnabled(False)
            if card.uninstallButton.isVisible():
                if state == "active":
                    card.uninstallButton.setText(
                        up.get("ActionUninstalling", "Removing…")
                    )
                    card.uninstallButton.setEnabled(False)
                elif state == "queued":
                    card.uninstallButton.setText(queued_fmt.format(0))
                    card.uninstallButton.setEnabled(False)
                else:
                    card.uninstallButton.setText(
                        up.get("ActionUninstall", "Uninstall")
                    )

    def restart_install(self, mode: EnhanceMode):
        """Start over an aborted download (no resume)."""
        if is_model_installed(mode):
            from backend.tools.model_download_registry import ModelDownloadRegistry

            ModelDownloadRegistry.instance().complete(KIND_ENHANCE, mode.value)
            self.refresh()
            return
        if job_state(KIND_ENHANCE, mode.value):
            return
        self._start_install(mode)

    def _start_install(self, mode: EnhanceMode):
        if self._processing or job_state(KIND_ENHANCE, mode.value):
            return
        if is_model_installed(mode):
            return

        def work():
            install_model(mode)

        enqueue_model_job(
            KIND_ENHANCE,
            mode.value,
            work,
            lambda err: self._finish_install(mode, err),
        )
        self._on_queue_changed()

    def _finish_install(self, mode: EnhanceMode, err: Optional[BaseException]):
        from backend.tools.model_download_registry import DownloadCancelled

        self.refresh()
        up = tr["Upscale"]
        name = tr["EnhanceMode"].get(mode.name, mode.value)
        if isinstance(err, DownloadCancelled):
            return
        if err:
            self.status_message.emit(up["InstallFailed"].format(str(err)))
        else:
            self.status_message.emit(up["InstallDone"].format(name))

    def _start_uninstall(self, mode: EnhanceMode):
        if self._processing or job_state(KIND_ENHANCE, mode.value):
            return
        up = tr["Upscale"]
        name = tr["EnhanceMode"].get(mode.name, mode.value)
        parent = self.cards[0].window() if self.cards else None
        if not ask_confirm(
            up.get("UninstallConfirmTitle", "Uninstall model?"),
            up.get(
                "UninstallConfirmDesc",
                "Delete local files for {}? You can install it again later.",
            ).format(name),
            parent,
        ):
            return

        def work():
            uninstall_model(mode)

        enqueue_model_job(
            KIND_ENHANCE,
            mode.value,
            work,
            lambda err: self._finish_uninstall(mode, err),
        )
        self._on_queue_changed()

    def _finish_uninstall(self, mode: EnhanceMode, err: Optional[BaseException]):
        self.refresh()
        up = tr["Upscale"]
        name = tr["EnhanceMode"].get(mode.name, mode.value)
        if err:
            self.status_message.emit(
                up.get("UninstallFailed", "Uninstall failed: {}").format(str(err))
            )
        else:
            self.status_message.emit(
                up.get("UninstallDone", "Uninstalled: {}").format(name)
            )
