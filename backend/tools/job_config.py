"""Per-job config snapshot so the infer worker uses the GUI's current model choices.

The worker is a long-lived process that imported ``backend.config`` once; without
overrides it keeps stale inpaint / detect / hardware flags after the user changes
settings. Every GPU job must carry the selected mode (and shared flags) in the
payload and apply them before loading models.
"""

from __future__ import annotations

from typing import Any, Dict


def snapshot_hardware() -> Dict[str, Any]:
    from backend.config import config

    return {
        "hardware_acceleration": bool(config.hardwareAcceleration.value),
    }


def snapshot_subtitle_config() -> Dict[str, Any]:
    """Serialize current subtitle-removal settings for a SUBTITLE job payload."""
    from backend.config import config

    return {
        **snapshot_hardware(),
        "inpaint_mode": config.inpaintMode.value.value,
        "subtitle_detect_mode": config.subtitleDetectMode.value.value,
        "sttn_neighbor_stride": int(config.sttnNeighborStride.value),
        "sttn_reference_length": int(config.sttnReferenceLength.value),
        "sttn_max_load_num": int(config.sttnMaxLoadNum.value),
        "propainter_max_load_num": int(config.propainterMaxLoadNum.value),
    }


def apply_hardware_from_payload(payload: Dict[str, Any]) -> None:
    """Apply hardware Acceleration flag from payload (top-level or nested config)."""
    hw = payload.get("hardware_acceleration")
    if hw is None:
        cfg = payload.get("config") or {}
        hw = cfg.get("hardware_acceleration")
    if hw is None:
        return

    from backend.config import config

    config.set(config.hardwareAcceleration, bool(hw), save=False)


def apply_subtitle_job_config(payload: Dict[str, Any]) -> None:
    """Apply payload config overrides onto the worker's in-memory config (no disk write)."""
    cfg = payload.get("config")
    if not cfg:
        apply_hardware_from_payload(payload)
        return

    from backend.config import config
    from backend.tools.constant import InpaintMode, SubtitleDetectMode

    if "inpaint_mode" in cfg:
        config.set(config.inpaintMode, InpaintMode(cfg["inpaint_mode"]), save=False)
    if "subtitle_detect_mode" in cfg:
        config.set(
            config.subtitleDetectMode,
            SubtitleDetectMode(cfg["subtitle_detect_mode"]),
            save=False,
        )
    if "hardware_acceleration" in cfg:
        config.set(
            config.hardwareAcceleration,
            bool(cfg["hardware_acceleration"]),
            save=False,
        )
    if "sttn_neighbor_stride" in cfg:
        config.set(config.sttnNeighborStride, int(cfg["sttn_neighbor_stride"]), save=False)
    if "sttn_reference_length" in cfg:
        config.set(config.sttnReferenceLength, int(cfg["sttn_reference_length"]), save=False)
    if "sttn_max_load_num" in cfg:
        config.set(config.sttnMaxLoadNum, int(cfg["sttn_max_load_num"]), save=False)
    if "propainter_max_load_num" in cfg:
        config.set(
            config.propainterMaxLoadNum,
            int(cfg["propainter_max_load_num"]),
            save=False,
        )
