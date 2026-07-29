"""Select Object model pairs in Settings (SAM2 + Grounding DINO)."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, Qt, Signal
from qfluentwidgets import FluentIcon

from backend.config import config, tr
from backend.tools.model_download_registry import KIND_SELECT_OBJECT
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
from ui.component.cards.model_install_helpers import (
    enqueue_model_job,
    install_button_text,
    job_state,
    register_queue_listener,
)
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
        key = self.info.pair_id.value
        queued = job_state(KIND_SELECT_OBJECT, key) is not None
        state = pair_install_state(self.info.pair_id)
        installed = state == "installed"
        partial = state == "partial"
        self.installButton.setEnabled(enabled and not installed and not queued)
        self.uninstallButton.setEnabled(enabled and (installed or partial) and not queued)

    def refresh(self):
        so = tr["SelectObject"]
        br = tr["BgRemove"]
        set_tr = tr["Setting"]
        desc = tr["SelectObjectPairDesc"].get(self.info.desc_key, "")
        state = pair_install_state(self.info.pair_id)
        key = self.info.pair_id.value
        queue_state = job_state(KIND_SELECT_OBJECT, key)
        queued_fmt = set_tr.get("ActionQueued", "Queued ({})")

        self.setContent(desc)

        if state == "installed":
            tip = so.get("StatusInstalled", br["StatusInstalled"])
            if self.info.is_default:
                tip = f"{tip} · {so.get('StatusDefault', br['StatusDefault'])}"
            self.contentLabel.setToolTip(tip)
            self.installButton.hide()
            self.uninstallButton.show()
            self.uninstallButton.setEnabled(not self._busy and not queue_state)
            if queue_state == "active":
                self.uninstallButton.setText(
                    so.get(
                        "ActionUninstalling",
                        br.get("ActionUninstalling", "Removing…"),
                    )
                )
            elif queue_state == "queued":
                self.uninstallButton.setText(queued_fmt.format(0))
            else:
                self.uninstallButton.setText(
                    so.get("ActionUninstall", br.get("ActionUninstall", "Uninstall"))
                )
        elif state == "partial":
            self.contentLabel.setToolTip(
                so.get(
                    "StatusPairPartial",
                    "Partial install — tap Install to complete this pair.",
                )
            )
            self.installButton.show()
            self.installButton.setEnabled(not self._busy and not queue_state)
            self.installButton.setText(
                install_button_text(
                    kind=KIND_SELECT_OBJECT,
                    key=key,
                    installing_text=br["ActionInstalling"],
                    queued_text=queued_fmt,
                    install_text=br["ActionInstall"],
                )
            )
            self.uninstallButton.show()
            self.uninstallButton.setEnabled(not self._busy and not queue_state)
            self.uninstallButton.setText(
                so.get("ActionUninstall", br.get("ActionUninstall", "Uninstall"))
            )
        else:
            self.contentLabel.setToolTip(desc)
            self.uninstallButton.hide()
            self.installButton.show()
            self.installButton.setEnabled(not self._busy and not queue_state)
            self.installButton.setText(
                install_button_text(
                    kind=KIND_SELECT_OBJECT,
                    key=key,
                    installing_text=br["ActionInstalling"],
                    queued_text=queued_fmt,
                    install_text=br["ActionInstall"],
                )
            )


class SelectObjectModelManager(QObject):
    models_changed = Signal()
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._was_busy = False
        self.cards: List[SelectObjectPairCard] = []
        for info in PAIR_CATALOG:
            card = SelectObjectPairCard(info, parent)
            card.install_requested.connect(self._start_install)
            card.uninstall_requested.connect(self._start_uninstall)
            self.cards.append(card)
        register_queue_listener(self._on_queue_changed)
        self.refresh()

    @property
    def is_busy(self) -> bool:
        return self._has_queue_activity()

    def refresh(self):
        for card in self.cards:
            card.refresh()
        self._apply_lock()
        self.models_changed.emit()

    def _has_queue_activity(self) -> bool:
        for card in self.cards:
            if job_state(KIND_SELECT_OBJECT, card.info.pair_id.value):
                return True
        return False

    def _on_queue_changed(self):
        busy = self._has_queue_activity()
        if busy != self._was_busy:
            self._was_busy = busy
            self.busy_changed.emit(busy)
        self._apply_lock()

    def _apply_lock(self):
        locked = False
        for card in self.cards:
            card.set_controls_enabled(not locked)
            card.refresh()

    def restart_install(self, pair_id: SelectObjectPairId):
        if is_pair_installed(pair_id):
            from backend.tools.model_download_registry import ModelDownloadRegistry

            ModelDownloadRegistry.instance().complete(
                KIND_SELECT_OBJECT, pair_id.value
            )
            self.refresh()
            return
        if job_state(KIND_SELECT_OBJECT, pair_id.value):
            return
        self._start_install(pair_id)

    def _start_install(self, pair_id: SelectObjectPairId):
        if job_state(KIND_SELECT_OBJECT, pair_id.value):
            return
        if is_pair_installed(pair_id):
            return

        def work():
            install_pair(pair_id)

        enqueue_model_job(
            KIND_SELECT_OBJECT,
            pair_id.value,
            work,
            lambda err: self._finish_install(pair_id, err),
        )
        self._on_queue_changed()

    def _finish_install(self, pair_id: SelectObjectPairId, err: Optional[BaseException]):
        from backend.tools.model_download_registry import DownloadCancelled

        self.refresh()
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
        if job_state(KIND_SELECT_OBJECT, pair_id.value):
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

        def work():
            uninstall_pair(pair_id)

        enqueue_model_job(
            KIND_SELECT_OBJECT,
            pair_id.value,
            work,
            lambda err: self._finish_uninstall(pair_id, err),
            operation="uninstall",
        )
        self._on_queue_changed()

    def _finish_uninstall(
        self, pair_id: SelectObjectPairId, err: Optional[BaseException]
    ):
        self.refresh()
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
