"""Seed first-run model downloads for the control-plane queue."""

from __future__ import annotations

from backend.tools.model_download_registry import (
    KIND_BG_REMOVE,
    KIND_ENHANCE,
    KIND_LOW_LIGHT,
    KIND_SELECT_OBJECT,
    ModelDownloadRegistry,
)

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
