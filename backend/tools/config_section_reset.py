"""Reset settings sections to factory defaults (ConfigItem.defaultValue)."""

from __future__ import annotations

from typing import Callable

from qfluentwidgets import qconfig

from backend.config import config


def reset_config_items(*items) -> None:
    for item in items:
        qconfig.set(item, item.defaultValue)


def reset_subtitle_detection() -> None:
    reset_config_items(
        config.subtitleYXAxisDifferencePixel,
        config.subtitleAreaDeviationPixel,
        config.subtitleAreaYAxisDifferencePixel,
        config.subtitleAreaPixelToleranceYPixel,
        config.subtitleAreaPixelToleranceXPixel,
        config.subtitleTimelineBackwardFrameCount,
        config.subtitleTimelineForwardFrameCount,
    )


def reset_sttn() -> None:
    reset_config_items(
        config.sttnNeighborStride,
        config.sttnReferenceLength,
        config.sttnMaxLoadNum,
    )


def reset_propainter() -> None:
    reset_config_items(config.propainterMaxLoadNum)


SECTION_RESETTERS: dict[str, Callable[[], None]] = {
    "subtitle_detection": reset_subtitle_detection,
    "sttn": reset_sttn,
    "propainter": reset_propainter,
}


def reset_section(section_id: str) -> None:
    resetter = SECTION_RESETTERS.get(section_id)
    if resetter is None:
        raise KeyError(section_id)
    resetter()
