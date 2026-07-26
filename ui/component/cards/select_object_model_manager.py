"""Select Object model pairs in Settings (SAM2 + Grounding DINO)."""

from __future__ import annotations

import threading
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from qfluentwidgets import FluentIcon

from backend.config import config, tr
from backend.tools.select_object_models import (
    PAIR_CATALOG,
    SelectObjectPairId,
    SelectObjectPairInfo,
    install_pair,
    is_complex_pair_installed,
    is_pair_installed,
    pair_install_state,
    uninstall_pair,
)
from ui.component.cards.midgard_card import MidgardSettingCard
from ui.component.controls.button_styles import make_button
from ui.component.utils.confirm_dialog import ask_confirm
from ui.theme import CARD


class SelectObjectPairCard(MidgardSettingCard):
    install_requested = Signal(object)
    uninstall_requested = Signal(object)

    def __init__(self, info: SelectObjectPairInfo, parent=None):
        title = tr["SelectObjectPair"].get(info.desc_key, info.pair_id.value)
        content = tr["SelectObjectPairDesc"].get(info.desc_key, "")
        super().__init__(FluentIcon.IOT, title, content, parent, detailed=True)
        self.info = info
        self._busy = False
        self._installing = False

        gap = CARD["trailing_gap"]
        self.uninstallButton = make_button(
            tr["SelectObject"].get(
                "ActionUninstall", tr["BgRemove"].get("ActionUninstall", "Uninstall")
            ),
            "secondary",
            self,
            FluentIcon.DELETE,
        )
        self.uninstallButton.clicked.connect(
            lambda checked=False, pid=self.info.pair_id: self.uninstall_requested.emit(
                pid
            )
        )
        self.hBoxLayout.addWidget(self.uninstallButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)

        self.installButton = make_button(
            tr["BgRemove"]["ActionInstall"],
            "primary",
            self,
            FluentIcon.DOWNLOAD,
        )
        self.installButton.clicked.connect(
            lambda checked=False, pid=self.info.pair_id: self.install_requested.emit(pid)
        )
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(gap)
        self.refresh()

    def set_controls_enabled(self, enabled: bool):
        self._busy = not enabled
        if not self._installing:
            state = pair_install_state(self.info.pair_id)
            installed = state == "installed"
            partial = state == "partial"
            self.installButton.setEnabled(enabled and not installed)
            self.uninstallButton.setEnabled(enabled and (installed or partial))

    def set_pair_installing(self, installing: bool):
        self._installing = installing
        br = tr["BgRemove"]
        so = tr["SelectObject"]
        if installing:
            self.installButton.show()
            self.installButton.setEnabled(False)
            self.installButton.setText(br["ActionInstalling"])
            self.uninstallButton.setEnabled(False)
            if self.uninstallButton.isVisible():
                self.uninstallButton.setText(
                    so.get(
                        "ActionUninstalling",
                        br.get("ActionUninstalling", "Removing…"),
                    )
                )
        else:
            self._installing = False
            self.refresh()

    def _set_status_tooltip(self, tooltip: str):
        self.contentLabel.setToolTip(tooltip or "")

    def refresh(self):
        if self._installing:
            return

        so = tr["SelectObject"]
        br = tr["BgRemove"]
        desc = tr["SelectObjectPairDesc"].get(self.info.desc_key, "")
        state = pair_install_state(self.info.pair_id)

        self.setContent(desc)

        if state == "installed":
            tip = so.get("StatusInstalled", br["StatusInstalled"])
            if self.info.is_default:
                tip = f"{tip} · {so.get('StatusDefault', br['StatusDefault'])}"
            self._set_status_tooltip(tip)
            self.installButton.hide()
            self.uninstallButton.show()
            self.uninstallButton.setEnabled(not self._busy)
            self.uninstallButton.setText(
                so.get("ActionUninstall", br.get("ActionUninstall", "Uninstall"))
            )
        elif state == "partial":
            self._set_status_tooltip(
                so.get(
                    "StatusPairPartial",
                    "Partial install — tap Install to complete this pair.",
                )
            )
            self.installButton.show()
            self.installButton.setEnabled(not self._busy)
            self.installButton.setText(tr["BgRemove"]["ActionInstall"])
            self.uninstallButton.show()
            self.uninstallButton.setEnabled(not self._busy)
            self.uninstallButton.setText(
                so.get("ActionUninstall", br.get("ActionUninstall", "Uninstall"))
            )
        else:
            self._set_status_tooltip(desc)
            self.uninstallButton.hide()
            self.installButton.show()
            self.installButton.setEnabled(not self._busy)
            self.installButton.setText(tr["BgRemove"]["ActionInstall"])


class SelectObjectModelManager(QObject):
    models_changed = Signal()
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._installing = False
        self._uninstalling = False
        self._installing_pair_id: Optional[SelectObjectPairId] = None
        self.cards: List[SelectObjectPairCard] = []
        for info in PAIR_CATALOG:
            card = SelectObjectPairCard(info, parent)
            card.install_requested.connect(self._start_install)
            card.uninstall_requested.connect(self._start_uninstall)
            self.cards.append(card)
        self.refresh()

    @property
    def is_busy(self) -> bool:
        return self._installing or self._uninstalling

    def refresh(self):
        for card in self.cards:
            if card.info.pair_id != self._installing_pair_id:
                card.refresh()
        self._apply_lock()
        self.models_changed.emit()

    def _apply_lock(self):
        so = tr["SelectObject"]
        br = tr["BgRemove"]
        for card in self.cards:
            active_install = (
                self._installing
                and not self._uninstalling
                and card.info.pair_id == self._installing_pair_id
            )
            card.set_controls_enabled(not self.is_busy)
            card.set_pair_installing(active_install)
            if (
                self._uninstalling
                and card.info.pair_id == self._installing_pair_id
                and card.uninstallButton.isVisible()
            ):
                card.uninstallButton.setText(
                    so.get(
                        "ActionUninstalling",
                        br.get("ActionUninstalling", "Removing…"),
                    )
                )
            elif card.uninstallButton.isVisible() and not self.is_busy:
                card.uninstallButton.setText(
                    so.get("ActionUninstall", br.get("ActionUninstall", "Uninstall"))
                )

    def restart_install(self, pair_id: SelectObjectPairId):
        """Start over an aborted pair download (no resume)."""
        if is_pair_installed(pair_id):
            from backend.tools.model_download_registry import (
                KIND_SELECT_OBJECT,
                ModelDownloadRegistry,
            )

            ModelDownloadRegistry.instance().complete(
                KIND_SELECT_OBJECT, pair_id.value
            )
            self.refresh()
            return
        if self.is_busy:
            QTimer.singleShot(1500, lambda p=pair_id: self.restart_install(p))
            return
        self._start_install(pair_id)

    def _start_install(self, pair_id: SelectObjectPairId):
        if self.is_busy:
            return
        self._installing = True
        self._uninstalling = False
        self._installing_pair_id = pair_id
        self._apply_lock()
        self.busy_changed.emit(True)

        def work():
            err = None
            try:
                install_pair(pair_id)
            except Exception as e:
                err = e
            QTimer.singleShot(0, lambda: self._finish_install(pair_id, err))

        threading.Thread(target=work, daemon=True).start()

    def _finish_install(self, pair_id: SelectObjectPairId, err: Optional[BaseException]):
        from backend.tools.model_download_registry import DownloadCancelled

        self._installing = False
        self._uninstalling = False
        self._installing_pair_id = None
        for card in self.cards:
            card.set_pair_installing(False)
        self.refresh()
        self.busy_changed.emit(False)
        if isinstance(err, DownloadCancelled):
            return
        so = tr["SelectObject"]
        br = tr["BgRemove"]
        name = tr["SelectObjectPair"].get(
            _pair_desc_key(pair_id), pair_id.value
        )
        if err:
            self.status_message.emit(
                so.get("InstallFailed", br["InstallFailed"]).format(str(err))
            )
        else:
            self.status_message.emit(
                so.get("InstallDone", br["InstallDone"]).format(name)
            )
            if (
                pair_id == SelectObjectPairId.COMPLEX
                and is_complex_pair_installed()
                and not config.selectObjectMoreComplex.value
            ):
                self.status_message.emit(
                    so.get("ComplexReady", "More complex models are ready to enable.")
                )

    def _start_uninstall(self, pair_id: SelectObjectPairId):
        if self.is_busy:
            return
        so = tr["SelectObject"]
        br = tr["BgRemove"]
        name = tr["SelectObjectPair"].get(_pair_desc_key(pair_id), pair_id.value)
        parent = self.cards[0].window() if self.cards else None
        if not ask_confirm(
            so.get(
                "UninstallConfirmTitle",
                br.get("UninstallConfirmTitle", "Uninstall model?"),
            ),
            so.get(
                "UninstallConfirmDesc",
                br.get(
                    "UninstallConfirmDesc",
                    "Delete local files for {}? You can install it again later.",
                ),
            ).format(name),
            parent,
        ):
            return
        self._installing = False
        self._uninstalling = True
        self._installing_pair_id = pair_id
        self._apply_lock()
        self.busy_changed.emit(True)

        def work():
            err = None
            try:
                uninstall_pair(pair_id)
            except Exception as e:
                err = e
            QTimer.singleShot(0, lambda: self._finish_uninstall(pair_id, err))

        threading.Thread(target=work, daemon=True).start()

    def _finish_uninstall(
        self, pair_id: SelectObjectPairId, err: Optional[BaseException]
    ):
        self._installing = False
        self._uninstalling = False
        self._installing_pair_id = None
        for card in self.cards:
            card.set_pair_installing(False)
        self.refresh()
        self.busy_changed.emit(False)
        so = tr["SelectObject"]
        br = tr["BgRemove"]
        name = tr["SelectObjectPair"].get(_pair_desc_key(pair_id), pair_id.value)
        if err:
            self.status_message.emit(
                so.get(
                    "UninstallFailed",
                    br.get("UninstallFailed", "Uninstall failed: {}"),
                ).format(str(err))
            )
        else:
            self.status_message.emit(
                so.get(
                    "UninstallDone",
                    br.get("UninstallDone", "Uninstalled: {}"),
                ).format(name)
            )


def _pair_desc_key(pair_id: SelectObjectPairId) -> str:
    for info in PAIR_CATALOG:
        if info.pair_id == pair_id:
            return info.desc_key
    return pair_id.value
