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


SIZE_PRESETS: tuple[SizePreset, ...] = (
    SizePreset("small", 512, 512, "GenerateSizeSmall"),
    SizePreset("medium", 768, 768, "GenerateSizeMedium"),
    SizePreset("large", 1024, 1024, "GenerateSizeLarge"),
)


def size_presets() -> List[SizePreset]:
    return list(SIZE_PRESETS)


def step_presets_for_mode(mode: GenerateMode) -> List[StepPreset]:
    info = catalog_info(mode)
    if info is None:
        return [
            StepPreset("fast", 4, "GenerateStepFast"),
            StepPreset("normal", 8, "GenerateStepNormal"),
            StepPreset("quality", 12, "GenerateStepQuality"),
        ]
    return [
        StepPreset("fast", int(info.step_fast), "GenerateStepFast"),
        StepPreset("normal", int(info.step_normal), "GenerateStepNormal"),
        StepPreset("quality", int(info.step_quality), "GenerateStepQuality"),
    ]


def resolve_guidance(mode: GenerateMode) -> float:
    info = catalog_info(mode)
    if info is None:
        return 1.0
    return float(info.default_guidance)

