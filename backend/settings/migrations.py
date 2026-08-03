"""Adapters from control-plane settings into operation settings."""

from __future__ import annotations

from backend.configuration.models import ApplicationConfiguration
from backend.configuration.service import get_settings
from backend.settings.model_schemas import (
    GenerateSettings, LowLightSettings, ProPainterSettings, STTNSettings, UpscaleSettings,
)


def from_application_configuration(
    config: ApplicationConfiguration | None = None,
) -> dict[str, object]:
    config = config or get_settings()
    subtitle = config.subtitle
    return {
        "generate": GenerateSettings(
            model=config.generation.mode,
            width=config.generation.width,
            height=config.generation.height,
            steps=config.generation.steps,
        ),
        "propainter": ProPainterSettings(max_frames=subtitle.propainter_max_load_num),
        "sttn": STTNSettings(
            max_frames=subtitle.sttn_max_load_num,
            reference_frames=subtitle.sttn_reference_length,
            neighbor_stride=subtitle.sttn_neighbor_stride,
            mask_expansion_px=subtitle.mask_expansion_px,
            timeline_before=subtitle.timeline_before_frames,
            timeline_after=subtitle.timeline_after_frames,
        ),
        "upscale": UpscaleSettings(
            model=config.enhancement.mode,
            scale_factor=2 if "x2" in config.enhancement.mode.lower() else 4,
            max_long_edge=config.enhancement.max_long_edge,
        ),
        "low_light": LowLightSettings(
            model=config.low_light.mode,
            max_long_edge=config.low_light.max_long_edge,
        ),
    }
