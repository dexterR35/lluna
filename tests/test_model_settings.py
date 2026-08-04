from __future__ import annotations

import pytest

from backend.settings.metadata import SettingsLevel
from backend.settings.model_schemas import (
    BackgroundRemovalSettings,
    GenerateSettings,
    LowLightSettings,
    ObjectSelectionSettings,
    ProPainterSettings,
    STTNSettings,
    UpscaleSettings,
)
from backend.settings.presets import Preset, ResolutionContext, resolve
from tests.fakes.hardware import CPU_ONLY, CUDA, DIRECTML, MPS, profile


@pytest.mark.parametrize(
    "settings",
    [
        GenerateSettings(),
        ProPainterSettings(),
        STTNSettings(),
        BackgroundRemovalSettings(),
        UpscaleSettings(),
        LowLightSettings(),
        ObjectSelectionSettings(),
    ],
)
def test_schemas_round_trip(settings) -> None:
    restored = type(settings).from_mapping(settings.to_snapshot())
    assert restored == settings
    assert all(spec.description for spec in settings.METADATA.values())
    assert all(spec.level in SettingsLevel for spec in settings.METADATA.values())


def test_invalid_setting_is_rejected() -> None:
    with pytest.raises(ValueError):
        GenerateSettings(width=32)
    with pytest.raises(TypeError):
        UpscaleSettings(scale_factor="2")


@pytest.mark.parametrize("preset", list(Preset))
@pytest.mark.parametrize("hardware", [CPU_ONLY, CUDA, DIRECTML, MPS])
def test_every_preset_and_hardware_is_deterministic(preset, hardware) -> None:
    context = ResolutionContext("upscale", "RealESRGAN_x2plus", hardware, 1920, 1080)
    first = resolve(UpscaleSettings(), configured=None, preset=preset, context=context)
    second = resolve(UpscaleSettings(), configured=None, preset=preset, context=context)
    assert first == second


def test_unsafe_frame_override_is_visible_and_clamped() -> None:
    low = profile(cuda=True, vram_mb=4096, ram_mb=8192)
    context = ResolutionContext("remove-text", "propainter", low, 1920, 1080)
    result = resolve(
        ProPainterSettings(),
        configured=ProPainterSettings(max_frames=70),
        preset=Preset.BALANCED,
        context=context,
    )
    value = result.values["max_frames"]
    assert value.configured == 70
    assert value.effective < 70
    assert value.safety_clamped
    assert value.reason
    assert result.warnings


def test_safe_override_is_preserved() -> None:
    context = ResolutionContext("remove-text", "propainter", CUDA, 1280, 720)
    result = resolve(
        ProPainterSettings(),
        configured=ProPainterSettings(max_frames=16),
        preset=Preset.BALANCED,
        context=context,
    )
    assert result.values["max_frames"].effective == 16
    assert not result.values["max_frames"].safety_clamped


def test_missing_model_is_reported() -> None:
    context = ResolutionContext("upscale", "RealESRGAN_x2plus", CPU_ONLY, model_installed=False)
    result = resolve(UpscaleSettings(), configured=None, preset=Preset.FAST, context=context)
    assert "not installed" in result.warnings[0]
