"""Legacy configuration adapters for typed settings."""

from __future__ import annotations

from backend.settings.model_schemas import (
    GenerateSettings,
    LowLightSettings,
    ProPainterSettings,
    STTNSettings,
    UpscaleSettings,
)


def from_legacy_config(config) -> dict[str, object]:
    """Snapshot existing qfluent values without mutating or saving them."""
    return {
        "generate": GenerateSettings(
            model=config.generateMode.value.value,
            width=int(config.generateWidth.value),
            height=int(config.generateHeight.value),
            steps=int(config.generateSteps.value),
        ),
        "propainter": ProPainterSettings(
            max_frames=int(config.propainterMaxLoadNum.value)
        ),
        "sttn": STTNSettings(
            max_frames=int(config.sttnMaxLoadNum.value),
            reference_frames=int(config.sttnReferenceLength.value),
            neighbor_stride=int(config.sttnNeighborStride.value),
            mask_expansion_px=int(config.subtitleAreaDeviationPixel.value),
            timeline_before=int(config.subtitleTimelineBackwardFrameCount.value),
            timeline_after=int(config.subtitleTimelineForwardFrameCount.value),
        ),
        "upscale": UpscaleSettings(
            model=config.enhanceMode.value.value,
            scale_factor=2 if "x2" in config.enhanceMode.value.value.lower() else 4,
            max_long_edge=int(config.enhanceMaxLongEdge.value),
        ),
        "low_light": LowLightSettings(
            model=config.lowLightMode.value.value,
            max_long_edge=int(config.lowLightMaxLongEdge.value),
        ),
    }
