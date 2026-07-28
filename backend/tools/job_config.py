"""Worker-safe immutable configuration snapshots.

Qt-backed settings are copied in the GUI process. Worker processes validate the
plain payload and never mutate the GUI configuration file.
"""

from __future__ import annotations

from typing import Any, Dict

from backend.configuration.models import SubtitleSettings


def snapshot_hardware() -> Dict[str, Any]:
    from backend.config import config

    return {
        "hardware_acceleration": bool(config.hardwareAcceleration.value),
    }


def snapshot_subtitle_config() -> Dict[str, Any]:
    """Serialize current subtitle-removal settings for a SUBTITLE job payload."""
    from backend.config import config
    from backend.configuration.legacy import snapshot_qt_configuration

    return snapshot_qt_configuration(config).subtitle.to_payload()


def apply_hardware_from_payload(payload: Dict[str, Any]) -> None:
    """Apply the per-job hardware flag to the runtime accelerator adapter."""
    hw = payload.get("hardware_acceleration")
    if hw is None:
        cfg = payload.get("config") or {}
        hw = cfg.get("hardware_acceleration")
    if hw is None:
        return

    from backend.tools.hardware_accelerator import HardwareAccelerator

    HardwareAccelerator.instance().set_enabled(bool(hw))


def apply_subtitle_job_config(payload: Dict[str, Any]) -> SubtitleSettings:
    """Validate a subtitle payload and return an immutable settings snapshot."""
    raw = payload.get("config") or {}
    if "hardware_acceleration" not in raw and "hardware_acceleration" in payload:
        raw = {**raw, "hardware_acceleration": payload["hardware_acceleration"]}
    settings = SubtitleSettings.from_mapping(raw)
    from backend.tools.hardware_accelerator import HardwareAccelerator

    HardwareAccelerator.instance().set_enabled(settings.hardware_acceleration)
    return settings
