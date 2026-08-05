"""Model-download recovery hooks owned by the control plane."""

from __future__ import annotations

from typing import List

from backend.tools.shared.download_registry import ModelDownloadRegistry, PendingDownload


def abort_downloads_on_shutdown() -> None:
    """Stop in-flight installs, delete partials, and persist pending work."""
    ModelDownloadRegistry.instance().abort_all_and_revert()


def prepare_restart_pending() -> List[PendingDownload]:
    """Clear cancellation state and return downloads needing a clean restart."""
    registry = ModelDownloadRegistry.instance()
    registry.clear_cancel()
    return registry.revert_pending_on_disk()


def cli_stop_and_revert_downloads() -> None:
    registry = ModelDownloadRegistry.instance()
    registry.abort_all_and_revert()
    with registry._lock:
        registry._save_pending_unlocked([])
    registry.clear_cancel()
