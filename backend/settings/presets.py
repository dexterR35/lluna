"""Deterministic, hardware-aware model-setting resolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any

from backend.hardware.policy import select_execution_policy
from backend.hardware.profile import HardwareProfile
from backend.settings.base import ModelSettings
from backend.settings.model_schemas import (
    GenerateSettings,
    LowLightSettings,
    ProPainterSettings,
    STTNSettings,
    UpscaleSettings,
)


class Preset(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    QUALITY = "quality"
    LOW_MEMORY = "low-memory"


@dataclass(frozen=True)
class ResolutionContext:
    task: str
    model: str
    hardware: HardwareProfile
    input_width: int = 0
    input_height: int = 0
    model_installed: bool = True

    @property
    def megapixels(self) -> float:
        return max(0.01, self.input_width * self.input_height / 1_000_000)


@dataclass(frozen=True)
class ValueResolution:
    default: Any
    recommended: Any
    configured: Any
    effective: Any
    safety_clamped: bool = False
    reason: str = ""


@dataclass(frozen=True)
class SettingsResolution:
    settings: ModelSettings
    values: dict[str, ValueResolution]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def _memory_class(context: ResolutionContext) -> str:
    gpu = context.hardware.primary_gpu
    available_vram = gpu.available_vram_mb if gpu else 0
    ram = context.hardware.memory.available_mb
    if gpu is None:
        if context.hardware.capabilities.torch_directml:
            return "low"
        return "medium" if ram >= 16_000 else "low"
    if available_vram >= 16_000 and ram >= 16_000:
        return "high"
    if available_vram >= 8_000 and ram >= 8_000:
        return "medium"
    return "low"


def _recommended(settings: ModelSettings, preset: Preset, context: ResolutionContext):
    memory = _memory_class(context)
    changes: dict[str, Any] = {}
    if isinstance(settings, (ProPainterSettings, STTNSettings)):
        base = {"low": 12, "medium": 24, "high": 48}[memory]
        if preset is Preset.FAST:
            base = max(8, base // 2)
        elif preset is Preset.QUALITY:
            base = min(70, int(base * 1.4))
        elif preset is Preset.LOW_MEMORY:
            base = min(8, base)
        resolution_factor = max(1.0, context.megapixels / 0.92)
        changes["max_frames"] = max(4, int(base / resolution_factor))
        changes["memory_mode"] = preset.value
    elif isinstance(settings, GenerateSettings):
        sizes = {
            Preset.FAST: 512,
            Preset.BALANCED: 768,
            Preset.QUALITY: 1024,
            Preset.LOW_MEMORY: 512,
        }
        size = sizes[preset]
        if memory == "low":
            size = min(size, 512)
        changes.update(
            width=size,
            height=size,
            cpu_offload=preset is Preset.LOW_MEMORY,
            attention_slicing=preset is Preset.LOW_MEMORY,
            cache_model=preset is not Preset.LOW_MEMORY,
            memory_mode=preset.value,
        )
    elif isinstance(settings, UpscaleSettings):
        tile = (
            0
            if memory == "high" and preset is not Preset.LOW_MEMORY
            else (256 if memory == "medium" else 128)
        )
        changes.update(tile_size=tile, memory_mode=preset.value)
    elif isinstance(settings, LowLightSettings):
        limit = {"low": 1280, "medium": 2048, "high": 4096}[memory]
        if preset is Preset.FAST:
            limit = min(limit, 1536)
        elif preset is Preset.LOW_MEMORY:
            limit = min(limit, 1024)
        changes.update(max_long_edge=limit, memory_mode=preset.value)
    return replace(settings, **changes) if changes else settings


def resolve(
    defaults: ModelSettings,
    *,
    configured: ModelSettings | None,
    preset: Preset,
    context: ResolutionContext,
) -> SettingsResolution:
    configured = configured or defaults
    recommended = _recommended(defaults, preset, context)
    default_values = asdict(defaults)
    configured_values = asdict(configured)
    recommended_values = asdict(recommended)
    effective = dict(configured_values)
    reasons = [f"{preset.value} preset resolved for {_memory_class(context)} memory."]
    warnings: list[str] = []
    if not context.model_installed:
        warnings.append(f"Model {context.model} is not installed.")
    backend = select_execution_policy(context.hardware).backend

    for name, value in recommended_values.items():
        if name == "memory_mode":
            effective[name] = value

    # Memory-sensitive maxima are safety ceilings, not silent preset overrides.
    for name in ("max_frames", "width", "height", "max_long_edge"):
        if name not in effective or name not in recommended_values:
            continue
        configured_value = effective[name]
        recommended_value = recommended_values[name]
        if configured_value > recommended_value and _memory_class(context) == "low":
            effective[name] = recommended_value
            warnings.append(
                f"{name}: configured {configured_value}, effective {recommended_value}; "
                "available memory is insufficient for the configured value."
            )

    cls = type(defaults)
    effective_settings = cls(**effective)
    values: dict[str, ValueResolution] = {}
    for name, default in default_values.items():
        configured_value = configured_values[name]
        effective_value = effective[name]
        clamped = configured_value != effective_value and name != "memory_mode"
        values[name] = ValueResolution(
            default=default,
            recommended=recommended_values[name],
            configured=configured_value,
            effective=effective_value,
            safety_clamped=clamped,
            reason=(
                f"{name} was limited for {_memory_class(context)} memory on {backend}."
                if clamped
                else ""
            ),
        )
    return SettingsResolution(
        settings=effective_settings,
        values=values,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )
