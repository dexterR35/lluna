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

_NATIVE_512_SIZE_PRESETS: tuple[SizePreset, ...] = (
    SizePreset("native", 512, 512, "GenerateSizeNative512"),
)


def _base_flux_step_presets(default_steps: int) -> tuple[StepPreset, ...]:
    """Full-step Base checkpoints expose BFL's 1..100 control range."""
    return tuple(
        StepPreset(
            f"steps-{steps}",
            steps,
            (
                "GenerateStepRecommended"
                if steps == default_steps
                else "GenerateStepCustom"
            ),
        )
        for steps in range(1, 101)
    )


_STEP_PRESETS: dict[GenerateMode, tuple[StepPreset, ...]] = {
    # Keep checkpoint semantics exact: distilled weights are the 4-step
    # checkpoint; full-step generation must use the corresponding Base repo.
    GenerateMode.FLUX2_KLEIN_4B: (
        StepPreset("steps-4", 4, "GenerateStepRecommended"),
    ),
    GenerateMode.FLUX2_KLEIN_9B: (
        StepPreset("steps-4", 4, "GenerateStepRecommended"),
    ),
    GenerateMode.FLUX2_KLEIN_BASE_4B: _base_flux_step_presets(50),
    GenerateMode.FLUX2_KLEIN_BASE_9B: _base_flux_step_presets(50),
    GenerateMode.SDXL_TURBO: (
        StepPreset("fast", 1, "GenerateStepFast"),
        StepPreset("normal", 2, "GenerateStepNormal"),
        StepPreset("quality", 4, "GenerateStepQuality"),
    ),
    GenerateMode.SD15: (
        StepPreset("fast", 20, "GenerateStepFast"),
        StepPreset("normal", 50, "GenerateStepNormal"),
        StepPreset("quality", 75, "GenerateStepQuality"),
    ),
}

_DEFAULT_STEP_KEYS: dict[GenerateMode, str] = {
    GenerateMode.FLUX2_KLEIN_4B: "steps-4",
    GenerateMode.FLUX2_KLEIN_9B: "steps-4",
    GenerateMode.FLUX2_KLEIN_BASE_4B: "steps-50",
    GenerateMode.FLUX2_KLEIN_BASE_9B: "steps-50",
    GenerateMode.SDXL_TURBO: "fast",
    GenerateMode.SD15: "normal",
}


def size_presets_for_mode(mode: GenerateMode) -> List[SizePreset]:
    if mode == GenerateMode.SD15:
        return list(_NATIVE_512_SIZE_PRESETS)
    return list(_GENERAL_SIZE_PRESETS)


def default_size_preset_for_mode(mode: GenerateMode) -> SizePreset:
    presets = size_presets_for_mode(mode)
    preferred_key = "small" if mode == GenerateMode.SDXL_TURBO else "large"
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
    presets = step_presets_for_mode(mode)
    preferred_key = _DEFAULT_STEP_KEYS.get(mode)
    for preset in presets:
        if preset.key == preferred_key:
            return preset
    return presets[0]


def validate_steps_for_mode(mode: GenerateMode, steps: int) -> int:
    value = int(steps)
    allowed = tuple(p.steps for p in step_presets_for_mode(mode))
    if value not in allowed:
        contiguous = allowed == tuple(range(min(allowed), max(allowed) + 1))
        allowed_text = (
            f"{min(allowed)}-{max(allowed)}"
            if contiguous
            else ", ".join(str(v) for v in allowed)
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

