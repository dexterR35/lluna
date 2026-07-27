"""Restart Settings model downloads that were aborted (close / CLI) — always start over."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from backend.tools.first_run_downloads import (
    dispatch_scheduled_downloads,
    seed_first_run_downloads,
)
from backend.tools.model_download_registry import (
    KIND_ENHANCE,
    KIND_GENERATE,
    KIND_LOW_LIGHT,
    KIND_BG_REMOVE,
    KIND_SELECT_OBJECT,
    ModelDownloadRegistry,
    PendingDownload,
)

if TYPE_CHECKING:
    from ui.advanced_setting_interface import AdvancedSettingInterface


def abort_downloads_on_shutdown() -> None:
    """Stop in-flight installs, delete partials, keep pending for next open."""
    try:
        ModelDownloadRegistry.instance().abort_all_and_revert()
    except Exception:
        pass


def prepare_restart_pending() -> List[PendingDownload]:
    """Clear cancel flag, wipe partials, return pending list (installs start clean)."""
    reg = ModelDownloadRegistry.instance()
    reg.clear_cancel()
    return reg.revert_pending_on_disk()


def restart_pending_downloads(settings: "AdvancedSettingInterface") -> None:
    """After GUI opens: enqueue pending downloads one at a time."""
    prepare_restart_pending()
    seed_first_run_downloads()
    pending = ModelDownloadRegistry.instance().list_pending()
    if not pending:
        return

    from PySide6.QtCore import QTimer

    def _kick() -> None:
        dispatch_scheduled_downloads(settings)

    QTimer.singleShot(800, _kick)


def _restart_one(settings: "AdvancedSettingInterface", item: PendingDownload) -> None:
    kind, key = item.kind, item.key
    try:
        if kind == KIND_ENHANCE:
            from backend.tools.constant import EnhanceMode

            settings.enhance_model_manager.restart_install(EnhanceMode(key))
        elif kind == KIND_LOW_LIGHT:
            from backend.tools.constant import LowLightMode

            settings.low_light_model_manager.restart_install(LowLightMode(key))
        elif kind == KIND_GENERATE:
            from backend.tools.constant import GenerateMode

            settings.generate_model_manager.restart_install(GenerateMode(key))
        elif kind == KIND_BG_REMOVE:
            from backend.tools.constant import BgRemoveMode

            settings.bg_remove_model_manager.restart_install(BgRemoveMode(key))
        elif kind == KIND_SELECT_OBJECT:
            from backend.tools.select_object_models import SelectObjectPairId

            settings.select_object_model_manager.restart_install(
                SelectObjectPairId(key)
            )
    except Exception:
        ModelDownloadRegistry.instance().fail(kind, key, keep_pending=False)


def cli_stop_and_revert_downloads() -> None:
    """install.py / CLI: stop GUI downloads, wipe partials, clear pending list."""
    reg = ModelDownloadRegistry.instance()
    reg.abort_all_and_revert()
    with reg._lock:
        reg._save_pending_unlocked([])
    reg.clear_cancel()
