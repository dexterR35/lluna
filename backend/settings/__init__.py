"""Typed model settings and hardware-aware preset resolution."""

from backend.settings.schemas.model import (
    GenerateSettings,
    LamaSettings,
    LowLightSettings,
    ObjectSelectionSettings,
    ProPainterSettings,
    STTNSettings,
    UpscaleSettings,
)
from backend.settings.presets import Preset, ResolutionContext, SettingsResolution, resolve

__all__ = [
    "GenerateSettings",
    "LamaSettings",
    "LowLightSettings",
    "ObjectSelectionSettings",
    "Preset",
    "ProPainterSettings",
    "ResolutionContext",
    "STTNSettings",
    "SettingsResolution",
    "UpscaleSettings",
    "resolve",
]
