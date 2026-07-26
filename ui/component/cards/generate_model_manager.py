"""Generate (FLUX.2) models as SettingCards - same pattern as Enhance / Low Light."""

from __future__ import annotations

import threading
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from qfluentwidgets import FluentIcon, PasswordLineEdit, SwitchButton
from qfluentwidgets.components.widgets.switch_button import IndicatorPosition

from backend.config import tr
from backend.tools.constant import GenerateMode
from backend.tools.generate_models import (
    MODEL_CATALOG,
    GenerateModelInfo,
    get_enabled_values,
    install_model,
    is_model_installed,
    set_model_enabled,
    uninstall_model,
)
from backend.tools.hf_auth import clear_hf_token, has_hf_token, save_hf_token
from ui.component.cards.midgard_card import MidgardSettingCard
from ui.component.controls.button_styles import make_button
from ui.component.utils.confirm_dialog import ask_confirm
from ui.theme import CARD


class GenerateModelCard(MidgardSettingCard):
    install_requested = Signal(object)
    uninstall_requested = Signal(object)
    enabled_changed = Signal()

    def __init__(self, info: GenerateModelInfo, parent=None):
        title = tr["GenerateMode"].get(info.mode.name, info.mode.name)
        content = tr["GenerateModelDesc"].get(info.desc_key, "")
        super().__init__(FluentIcon.EDIT, title, content, parent, detailed=True)
        self.info = info
        self._busy = False

        off = tr["Generate"].get("ToggleOff", tr["BgRemove"]["ToggleOff"])
        on = tr["Generate"].get("ToggleOn", tr["BgRemove"]["ToggleOn"])
        self.switchButton = SwitchButton(off, self, IndicatorPosition.RIGHT)
        self.switchButton.setOnText(on)
        self.switchButton.setOffText(off)
        self.switchButton.checkedChanged.connect(self._on_switch)
        gap = CARD["trailing_gap"]
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.uninstallButton = make_button(
            tr["Generate"].get(
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
            tr["Generate"].get("ActionInstall", tr["BgRemove"]["ActionInstall"]),
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
        if checked:
            from backend.config import config

            config.set(config.generateMode, self.info.mode)
        self.enabled_changed.emit()
        self.refresh()

    def set_controls_enabled(self, enabled: bool):
        self._busy = not enabled
        installed = is_model_installed(self.info.mode)
        self.installButton.setEnabled(enabled and not installed)
        self.uninstallButton.setEnabled(enabled and installed)
        self.switchButton.setEnabled(enabled and installed)

    def refresh(self):
        gen = tr["Generate"]
        br = tr["BgRemove"]
        installed = is_model_installed(self.info.mode)
        enabled = self.info.mode.value in get_enabled_values()
        desc = tr["GenerateModelDesc"].get(self.info.desc_key, "")

        if installed:
            suffix = gen.get("StatusInstalled", br["StatusInstalled"])
            if self.info.is_default:
                suffix = f"{suffix} · {gen.get('StatusDefault', br['StatusDefault'])}"
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
            self.installButton.setText(gen.get("ActionInstall", br["ActionInstall"]))


class HfTokenCard(MidgardSettingCard):
    """Save a Hugging Face read token for authenticated Hub downloads."""

    token_changed = Signal()
    status_message = Signal(str)

    def __init__(self, parent=None):
        gen = tr["Generate"]
        super().__init__(
            FluentIcon.CERTIFICATE,
            gen.get("HfTokenTitle", "Hugging Face Token"),
            gen.get("HfTokenDesc", ""),
            parent,
            detailed=True,
        )
        gap = CARD["trailing_gap"]
        self.tokenEdit = PasswordLineEdit(self)
        self.tokenEdit.setPlaceholderText(
            gen.get("HfTokenPlaceholder", "hf_… read token")
        )
        self.tokenEdit.setClearButtonEnabled(True)
        self.tokenEdit.setMinimumWidth(220)
        self.hBoxLayout.addWidget(self.tokenEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.saveButton = make_button(
            gen.get("HfTokenSave", "Save"), "primary", self, FluentIcon.SAVE
        )
        self.saveButton.clicked.connect(self._save)
        self.hBoxLayout.addWidget(self.saveButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.clearButton = make_button(
            gen.get("HfTokenClear", "Clear"), "secondary", self
        )
        self.clearButton.clicked.connect(self._clear)
        self.hBoxLayout.addWidget(self.clearButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.refresh()

    def refresh(self):
        gen = tr["Generate"]
        if has_hf_token():
            self.setContent(gen.get("HfTokenSaved", "Token saved (authenticated downloads)."))
            self.clearButton.setEnabled(True)
        else:
            self.setContent(
                gen.get(
                    "HfTokenDesc",
                    "Optional read token for faster Hub downloads and gated models (9B).",
                )
            )
            self.clearButton.setEnabled(False)

    def _save(self):
        gen = tr["Generate"]
        text = self.tokenEdit.text().strip()
        if not text:
            self.status_message.emit(gen.get("HfTokenEmpty", "Paste an HF token first."))
            return
        try:
            save_hf_token(text)
            self.tokenEdit.clear()
            self.refresh()
            self.token_changed.emit()
            self.status_message.emit(gen.get("HfTokenSaveDone", "Hugging Face token saved."))
        except Exception as e:
            self.status_message.emit(
                gen.get("HfTokenSaveFailed", "Could not save token: {}").format(e)
            )

    def _clear(self):
        gen = tr["Generate"]
        clear_hf_token()
        self.tokenEdit.clear()
        self.refresh()
        self.token_changed.emit()
        self.status_message.emit(gen.get("HfTokenCleared", "Hugging Face token cleared."))


class GenerateModelManager(QObject):
    models_changed = Signal()
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._installing = False
        self._processing = False
        self.cards: List[GenerateModelCard] = []
        self.token_card = HfTokenCard(parent)
        self.token_card.status_message.connect(self.status_message.emit)

        for info in MODEL_CATALOG:
            card = GenerateModelCard(info, parent)
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
        gen = tr["Generate"]
        br = tr["BgRemove"]
        locked = self._installing or self._processing
        for card in self.cards:
            card.set_controls_enabled(not locked)
            if self._installing and card.installButton.isVisible():
                card.installButton.setText(
                    gen.get("ActionInstalling", br["ActionInstalling"])
                )
            elif card.installButton.isVisible():
                card.installButton.setText(
                    gen.get("ActionInstall", br["ActionInstall"])
                )
            if self._installing and card.uninstallButton.isVisible():
                card.uninstallButton.setText(
                    gen.get(
                        "ActionUninstalling",
                        br.get("ActionUninstalling", "Removing…"),
                    )
                )
            elif card.uninstallButton.isVisible():
                card.uninstallButton.setText(
                    gen.get(
                        "ActionUninstall",
                        br.get("ActionUninstall", "Uninstall"),
                    )
                )

    def restart_install(self, mode: GenerateMode):
        """Start over an aborted download (no resume)."""
        if is_model_installed(mode):
            from backend.tools.model_download_registry import (
                KIND_GENERATE,
                ModelDownloadRegistry,
            )

            ModelDownloadRegistry.instance().complete(KIND_GENERATE, mode.value)
            self.refresh()
            return
        if self._installing or self._processing:
            QTimer.singleShot(1500, lambda m=mode: self.restart_install(m))
            return
        self._start_install(mode)

    def _start_install(self, mode: GenerateMode):
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

    def _finish_install(self, mode: GenerateMode, err: Optional[BaseException]):
        from backend.tools.model_download_registry import DownloadCancelled

        self._installing = False
        if err is None:
            set_model_enabled(mode, True)
            from backend.config import config

            config.set(config.generateMode, mode)
        self.refresh()
        self.busy_changed.emit(False)
        if isinstance(err, DownloadCancelled):
            return
        gen = tr["Generate"]
        br = tr["BgRemove"]
        name = tr["GenerateMode"].get(mode.name, mode.value)
        if err:
            self.status_message.emit(
                gen.get("InstallFailed", br["InstallFailed"]).format(str(err))
            )
        else:
            self.status_message.emit(
                gen.get("InstallDone", br["InstallDone"]).format(name)
            )

    def _start_uninstall(self, mode: GenerateMode):
        if self._installing or self._processing:
            return
        gen = tr["Generate"]
        br = tr["BgRemove"]
        name = tr["GenerateMode"].get(mode.name, mode.value)
        parent = self.cards[0].window() if self.cards else None
        if not ask_confirm(
            gen.get(
                "UninstallConfirmTitle",
                br.get("UninstallConfirmTitle", "Uninstall model?"),
            ),
            gen.get(
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

    def _finish_uninstall(self, mode: GenerateMode, err: Optional[BaseException]):
        self._installing = False
        self.refresh()
        self.busy_changed.emit(False)
        gen = tr["Generate"]
        br = tr["BgRemove"]
        name = tr["GenerateMode"].get(mode.name, mode.value)
        if err:
            self.status_message.emit(
                gen.get(
                    "UninstallFailed",
                    br.get("UninstallFailed", "Uninstall failed: {}"),
                ).format(str(err))
            )
        else:
            self.status_message.emit(
                gen.get(
                    "UninstallDone",
                    br.get("UninstallDone", "Uninstalled: {}"),
                ).format(name)
            )
