"""Shared Generate UI/backend option presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from backend.tools.constant import GenerateMode
from backend.tools.generate_models import catalog_info


@dataclass(frozen=True)
class SizePreset:
    key: str
    width: int
    height: int
    label_key: str


@dataclass(frozen=True)
class StepPreset:
    key: str
    steps: int
    label_key: str


_GENERAL_SIZE_PRESETS: tuple[SizePreset, ...] = (
    SizePreset("small", 512, 512, "GenerateSizeSmall"),
    SizePreset("medium", 768, 768, "GenerateSizeMedium"),
    SizePreset("large", 1024, 1024, "GenerateSizeLarge"),
)

_STEP_PRESETS: dict[GenerateMode, tuple[StepPreset, ...]] = {
    GenerateMode.FLUX2_KLEIN_4B: (StepPreset("max", 4, "GenerateStepQuality"),),
    GenerateMode.FLUX2_KLEIN_9B: (StepPreset("max", 4, "GenerateStepQuality"),),
    GenerateMode.FLUX2_KLEIN_BASE_4B: (StepPreset("max", 50, "GenerateStepQuality"),),
    GenerateMode.FLUX2_KLEIN_BASE_9B: (StepPreset("max", 50, "GenerateStepQuality"),),
    GenerateMode.FLUX2_DEV: (StepPreset("max", 50, "GenerateStepQuality"),),
    GenerateMode.FLUX2_KLEIN_9B_FP8: (StepPreset("max", 4, "GenerateStepQuality"),),
    GenerateMode.QWEN_IMAGE: (StepPreset("max", 50, "GenerateStepQuality"),),
}


def size_presets_for_mode(mode: GenerateMode) -> List[SizePreset]:
    return list(_GENERAL_SIZE_PRESETS)


def default_size_preset_for_mode(mode: GenerateMode) -> SizePreset:
    presets = size_presets_for_mode(mode)
    preferred_key = "large"
    for preset in presets:
        if preset.key == preferred_key:
            return preset
    return presets[0]


def step_presets_for_mode(mode: GenerateMode) -> List[StepPreset]:
    return list(
        _STEP_PRESETS.get(
            mode,
            (StepPreset("recommended", 4, "GenerateStepRecommended"),),
        )
    )


def default_step_preset_for_mode(mode: GenerateMode) -> StepPreset:
    """Return the model's only supported UI policy: its maximum step count."""
    presets = step_presets_for_mode(mode)
    return max(presets, key=lambda preset: preset.steps)


def validate_steps_for_mode(mode: GenerateMode, steps: int) -> int:
    value = int(steps)
    allowed = tuple(p.steps for p in step_presets_for_mode(mode))
    if value not in allowed:
        contiguous = allowed == tuple(range(min(allowed), max(allowed) + 1))
        allowed_text = (
            f"{min(allowed)}-{max(allowed)}" if contiguous else ", ".join(str(v) for v in allowed)
        )
        raise ValueError(
            f"{mode.value} supports the configured step preset(s): {allowed_text}; "
            f"received {value}."
        )
    return value


def resolve_guidance(mode: GenerateMode) -> float:
    info = catalog_info(mode)
    if info is None:
        return 1.0
    return float(info.default_guidance)
