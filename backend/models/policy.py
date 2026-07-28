"""Memory-sensitive model execution policy."""

from __future__ import annotations

from dataclasses import dataclass

from backend.hardware.profile import HardwareProfile
from backend.models.metadata import ModelMetadata
from backend.settings.model_schemas import ProPainterSettings, STTNSettings
from backend.settings.presets import Preset, ResolutionContext, resolve


@dataclass(frozen=True)
class EffectiveValue:
    configured: int
    recommended: int
    maximum_safe: int
    effective: int
    reason: str = ""


@dataclass(frozen=True)
class ModelCompatibility:
    compatible: bool
    backend: str
    installed: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def evaluate_model_compatibility(
    model: ModelMetadata,
    profile: HardwareProfile,
    *,
    installed: bool,
    acceleration_enabled: bool = True,
) -> ModelCompatibility:
    """Make a deterministic model/backend decision from normalized facts."""
    from backend.hardware.policy import select_execution_policy

    execution = select_execution_policy(
        profile,
        acceleration_enabled=acceleration_enabled,
    )
    reasons: list[str] = []
    warnings: list[str] = []
    compatible = True
    if not installed:
        compatible = False
        reasons.append("The model is not installed.")
    if execution.backend not in model.compatible_backends:
        compatible = False
        reasons.append(
            f"{model.display_name} does not support the {execution.backend} backend."
        )
    available_ram = profile.memory.available_mb
    if model.minimum_ram_mb and available_ram < model.minimum_ram_mb:
        compatible = False
        reasons.append(
            f"{model.minimum_ram_mb} MB RAM is required; "
            f"{available_ram:.0f} MB is available."
        )
    gpu = profile.primary_gpu
    available_vram = gpu.available_vram_mb if gpu else 0.0
    if model.minimum_vram_mb:
        if execution.backend == "cpu":
            if "cpu" not in model.compatible_backends:
                compatible = False
            warnings.append("No accelerator memory is available.")
        elif not gpu or available_vram <= 0:
            warnings.append(
                "Available accelerator memory could not be measured; "
                "the first run may fall back or fail."
            )
        elif available_vram < model.minimum_vram_mb:
            compatible = False
            reasons.append(
                f"{model.minimum_vram_mb} MB VRAM is required; "
                f"{available_vram:.0f} MB is available."
            )
    if compatible:
        reasons.append(
            f"{model.display_name} is compatible with {execution.backend}."
        )
    return ModelCompatibility(
        compatible=compatible,
        backend=execution.backend,
        installed=installed,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def video_frame_policy(
    profile: HardwareProfile,
    *,
    configured: int,
    width: int,
    height: int,
    propainter: bool,
) -> EffectiveValue:
    settings = (
        ProPainterSettings(max_frames=configured)
        if propainter
        else STTNSettings(max_frames=configured)
    )
    result = resolve(
        type(settings)(),
        configured=settings,
        preset=Preset.BALANCED,
        context=ResolutionContext(
            task="remove-text",
            model="propainter" if propainter else "sttn",
            hardware=profile,
            input_width=width,
            input_height=height,
        ),
    )
    value = result.values["max_frames"]
    maximum = int(value.recommended)
    return EffectiveValue(
        configured=int(value.configured),
        recommended=int(value.recommended),
        maximum_safe=maximum,
        effective=int(value.effective),
        reason=value.reason,
    )
