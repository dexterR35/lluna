"""Reset functional settings sections to validated factory defaults."""

from __future__ import annotations

from backend.configuration.models import ApplicationConfiguration
from backend.configuration.service import get_settings, update_settings


def reset_subtitle_detection() -> None:
    defaults = ApplicationConfiguration().subtitle
    update_settings({"subtitle": {
        "vertical_box_tolerance_px": defaults.vertical_box_tolerance_px,
        "mask_expansion_px": defaults.mask_expansion_px,
        "area_y_axis_difference_px": defaults.area_y_axis_difference_px,
        "box_tolerance_y_px": defaults.box_tolerance_y_px,
        "box_tolerance_x_px": defaults.box_tolerance_x_px,
        "timeline_before_frames": defaults.timeline_before_frames,
        "timeline_after_frames": defaults.timeline_after_frames,
    }})


def reset_sttn() -> None:
    defaults = ApplicationConfiguration().subtitle
    update_settings({"subtitle": {
        "sttn_neighbor_stride": defaults.sttn_neighbor_stride,
        "sttn_reference_length": defaults.sttn_reference_length,
        "sttn_max_load_num": defaults.sttn_max_load_num,
    }})


def reset_propainter() -> None:
    update_settings({"subtitle": {
        "propainter_max_load_num": ApplicationConfiguration().subtitle.propainter_max_load_num
    }})


SECTION_RESETTERS = {
    "subtitle_detection": reset_subtitle_detection,
    "sttn": reset_sttn,
    "propainter": reset_propainter,
}


def reset_section(section_id: str) -> None:
    try:
        SECTION_RESETTERS[section_id]()
    except KeyError as exc:
        raise KeyError(section_id) from exc
