"""Shared Generate UI/backend option presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from backend.tools.shared.constants import GenerateMode
from backend.tools.installers.generate import catalog_info


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


def _steps_capability(mode: GenerateMode):
    from backend.models.reference.capabilities import builtin_contract

    _variant, capabilities = builtin_contract(f"generate:{mode.value}")
    return capabilities.steps


def size_presets_for_mode(mode: GenerateMode) -> List[SizePreset]:
    return list(_GENERAL_SIZE_PRESETS)


def default_size_preset_for_mode(mode: GenerateMode) -> SizePreset:
    presets = size_presets_for_mode(mode)
    preferred_key = "large"
    for preset in presets:
        if preset.key == preferred_key:
            return preset
    return presets[0]


def default_step_preset_for_mode(mode: GenerateMode) -> StepPreset:
    """Return this model's default step count, per its capability contract."""
    steps = _steps_capability(mode)
    default = int(steps.default) if steps else 4
    return StepPreset("default", default, "GenerateStepRecommended")


def validate_steps_for_mode(mode: GenerateMode, steps: int) -> int:
    value = int(steps)
    capability = _steps_capability(mode)
    if capability is None:
        return value
    minimum, maximum = int(capability.minimum), int(capability.maximum)
    if not minimum <= value <= maximum:
        range_text = str(minimum) if minimum == maximum else f"{minimum}-{maximum}"
        raise ValueError(
            f"{mode.value} supports {range_text} steps; received {value}."
        )
    return value


def resolve_guidance(mode: GenerateMode) -> float:
    info = catalog_info(mode)
    if info is None:
        return 1.0
    return float(info.default_guidance)
