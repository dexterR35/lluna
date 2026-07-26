"""Reset settings sections to factory defaults (ConfigItem.defaultValue)."""

from __future__ import annotations

from typing import Callable

from qfluentwidgets import qconfig

from backend.config import config
from backend.tools.bg_remove_models import DEFAULT_ENABLED_VALUES as BG_DEFAULT_ENABLED
from backend.tools.bg_remove_models import serialize_enabled_values as serialize_bg_enabled
from backend.tools.enhance_models import DEFAULT_ENABLED_VALUES as ENHANCE_DEFAULT_ENABLED
from backend.tools.enhance_models import serialize_enabled_values as serialize_enhance_enabled
from backend.tools.low_light_models import DEFAULT_ENABLED_VALUES as LOW_LIGHT_DEFAULT_ENABLED
from backend.tools.low_light_models import serialize_enabled_values as serialize_low_light_enabled
from backend.tools.generate_models import DEFAULT_ENABLED_VALUES as GENERATE_DEFAULT_ENABLED
from backend.tools.generate_models import serialize_enabled_values as serialize_generate_enabled


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


def reset_bg_remove_models() -> None:
    reset_config_items(config.bgRemoveMode)
    config.set(
        config.bgRemoveEnabledModels,
        serialize_bg_enabled(BG_DEFAULT_ENABLED),
    )


def reset_enhance_models() -> None:
    reset_config_items(config.enhanceMode)
    config.set(
        config.enhanceEnabledModels,
        serialize_enhance_enabled(ENHANCE_DEFAULT_ENABLED),
    )


def reset_low_light_models() -> None:
    reset_config_items(config.lowLightMode, config.lowLightMaxLongEdge)
    config.set(
        config.lowLightEnabledModels,
        serialize_low_light_enabled(LOW_LIGHT_DEFAULT_ENABLED),
    )


def reset_generate_models() -> None:
    reset_config_items(
        config.generateMode,
        config.generateWidth,
        config.generateHeight,
        config.generateSteps,
    )
    config.set(
        config.generateEnabledModels,
        serialize_generate_enabled(GENERATE_DEFAULT_ENABLED),
    )


def reset_select_object_models() -> None:
    reset_config_items(config.selectObjectMoreComplex)


def reset_advanced() -> None:
    reset_config_items(
        config.saveDirectory,
        config.checkUpdateOnStartup,
    )


SECTION_RESETTERS: dict[str, Callable[[], None]] = {
    "subtitle_detection": reset_subtitle_detection,
    "sttn": reset_sttn,
    "propainter": reset_propainter,
    "bg_remove_models": reset_bg_remove_models,
    "enhance_models": reset_enhance_models,
    "low_light_models": reset_low_light_models,
    "generate_models": reset_generate_models,
    "select_object_models": reset_select_object_models,
    "advanced": reset_advanced,
}


def reset_section(section_id: str) -> None:
    resetter = SECTION_RESETTERS.get(section_id)
    if resetter is None:
        raise KeyError(section_id)
    resetter()
