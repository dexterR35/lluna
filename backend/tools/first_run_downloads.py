"""First-run default model downloads — seeded at install, dispatched via GUI queue."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from backend.tools.model_download_registry import (
    KIND_BG_REMOVE,
    KIND_ENHANCE,
    KIND_LOW_LIGHT,
    KIND_SELECT_OBJECT,
    ModelDownloadRegistry,
    PendingDownload,
)

if TYPE_CHECKING:
    from ui.advanced_setting_interface import AdvancedSettingInterface

# Must match install.py / BgRemoveMode defaults.
REMBG_PREFETCH_MODELS = [
    "birefnet-general",
    "u2net_human_seg",
    "isnet-anime",
    "u2net_cloth_seg",
]


def seed_first_run_downloads(*, skip_rembg: bool = False) -> int:
    """Schedule missing default models. Returns count of newly scheduled items."""
    from backend.tools.constant import EnhanceMode, LowLightMode
    from backend.tools.enhance_models import is_model_installed as enhance_installed
    from backend.tools.low_light_models import is_model_installed as low_light_installed
    from backend.tools.bg_remove_models import is_model_installed as bg_installed
    from backend.tools.select_object_models import (
        SelectObjectPairId,
        is_pair_installed,
    )

    reg = ModelDownloadRegistry.instance()
    scheduled = 0

    if not skip_rembg:
        for name in REMBG_PREFETCH_MODELS:
            from backend.tools.constant import BgRemoveMode

            try:
                mode = BgRemoveMode(name)
            except ValueError:
                continue
            if not bg_installed(mode):
                reg.schedule(KIND_BG_REMOVE, name)
                scheduled += 1

    if not enhance_installed(EnhanceMode.X2PLUS):
        reg.schedule(KIND_ENHANCE, EnhanceMode.X2PLUS.value)
        scheduled += 1

    if not low_light_installed(LowLightMode.MIRNET_LOL):
        reg.schedule(KIND_LOW_LIGHT, LowLightMode.MIRNET_LOL.value)
        scheduled += 1

    if not is_pair_installed(SelectObjectPairId.FAST):
        reg.schedule(KIND_SELECT_OBJECT, SelectObjectPairId.FAST.value)
        scheduled += 1

    return scheduled


def dispatch_scheduled_downloads(settings: "AdvancedSettingInterface") -> None:
    """Enqueue every pending model download (FIFO, one at a time)."""
    pending = ModelDownloadRegistry.instance().list_pending()
    for item in pending:
        _dispatch_one(settings, item)


def _dispatch_one(settings: "AdvancedSettingInterface", item: PendingDownload) -> None:
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


def pending_label(item: PendingDownload) -> str:
    """Human-readable label for queue banner."""
    kind, key = item.kind, item.key
    try:
        from backend.config import tr

        if kind == KIND_ENHANCE:
            from backend.tools.constant import EnhanceMode

            mode = EnhanceMode(key)
            return tr["EnhanceMode"].get(mode.name, key)
        if kind == KIND_LOW_LIGHT:
            from backend.tools.constant import LowLightMode

            mode = LowLightMode(key)
            return tr["LowLightMode"].get(mode.name, key)
        if kind == KIND_BG_REMOVE:
            from backend.tools.constant import BgRemoveMode

            mode = BgRemoveMode(key)
            return tr["BgRemoveMode"].get(mode.name, key)
        if kind == KIND_SELECT_OBJECT:
            from backend.tools.select_object_models import PAIR_CATALOG

            for info in PAIR_CATALOG:
                if info.pair_id.value == key:
                    return tr["SelectObjectPair"].get(info.desc_key, key)
        if kind == KIND_GENERATE:
            from backend.tools.constant import GenerateMode

            mode = GenerateMode(key)
            return tr["GenerateMode"].get(mode.name, key)
    except Exception:
        pass
    return key


def list_pending_labels() -> List[str]:
    reg = ModelDownloadRegistry.instance()
    return [pending_label(p) for p in reg.list_pending()]
