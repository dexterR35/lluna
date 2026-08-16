"""Seed first-run model downloads for the control-plane queue."""

from __future__ import annotations

from backend.tools.shared.download_registry import (
    KIND_ENHANCE,
    KIND_LOW_LIGHT,
    ModelDownloadRegistry,
)

def seed_first_run_downloads() -> int:
    """Schedule missing default models. Returns count of newly scheduled items.

    SAM 3.1 is deliberately not seeded here (unlike the old SAM2 pair): like
    SUPIR/SeedVR2, it's a large, gated, isolated-runtime install and stays
    opt-in from the model manager rather than auto-downloading on first run.
    """
    from backend.tools.shared.constants import EnhanceMode, LowLightMode
    from backend.tools.installers.enhance import is_model_installed as enhance_installed
    from backend.tools.installers.low_light import is_model_installed as low_light_installed

    reg = ModelDownloadRegistry.instance()
    scheduled = 0

    if not enhance_installed(EnhanceMode.X2PLUS):
        reg.schedule(KIND_ENHANCE, EnhanceMode.X2PLUS.value)
        scheduled += 1

    if not low_light_installed(LowLightMode.MIRNET_LOL):
        reg.schedule(KIND_LOW_LIGHT, LowLightMode.MIRNET_LOL.value)
        scheduled += 1

    return scheduled
