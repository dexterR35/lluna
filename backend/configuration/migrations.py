"""One-way migrations into the current typed settings schema."""

from __future__ import annotations

from typing import Any, Mapping

from backend.configuration.models import SCHEMA_VERSION

_MODERN_SECTIONS = {
    "runtime",
    "subtitle",
    "enhancement",
    "low_light",
    "generation",
    "object_selection",
    "models",
}


def is_legacy_mapping(raw: Mapping[str, Any]) -> bool:
    return not any(section in raw for section in _MODERN_SECTIONS)


def migrate_mapping(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return schema v2 without mutating the supplied mapping."""
    if not is_legacy_mapping(raw):
        migrated = dict(raw)
        migrated["schema_version"] = SCHEMA_VERSION
        return migrated

    main = dict(raw.get("Main", {}))
    infer = dict(raw.get("Infer", {}))
    sttn = dict(raw.get("Sttn", {}))
    propainter = dict(raw.get("ProPainter", {}))
    enhancement = dict(raw.get("Enhance", {}))
    low_light = dict(raw.get("LowLight", {}))
    generation = dict(raw.get("Generate", {}))
    object_selection = dict(raw.get("SelectObject", {}))
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime": {
            "job_watchdog_seconds": infer.get("JobWatchdogSec", 90),
            "idle_release_seconds": infer.get("IdleReleaseSec", 60),
            "check_updates_on_startup": main.get("CheckUpdateOnStartup", True),
            "soft_defaults_applied": infer.get("SoftDefaultsApplied", False),
        },
        "subtitle": {
            "selection_areas": main.get("SubtitleSelectionAreas", "0.88,0.99,0.15,0.85"),
            "inpaint_mode": main.get("InpaintMode", "sttn-auto"),
            "subtitle_detect_mode": main.get("SubtitleDetectMode", "PP_OCRv5_SERVER"),
            "hardware_acceleration": main.get("HardwareAcceleration", True),
            "sttn_neighbor_stride": sttn.get("NeighborStride", 5),
            "sttn_reference_length": sttn.get("ReferenceLength", 10),
            "sttn_max_load_num": sttn.get("MaxLoadNum", 50),
            "propainter_max_load_num": propainter.get("MaxLoadNum", 70),
            "mask_expansion_px": main.get("SubtitleAreaDeviationPixel", 10),
            "area_y_axis_difference_px": main.get("SubtitleAreaYAxisDifferencePixel", 20),
            "timeline_before_frames": main.get("SubtitleTimelineBackwardFrameCount", 3),
            "timeline_after_frames": main.get("SubtitleTimelineForwardFrameCount", 3),
            "vertical_box_tolerance_px": main.get("SubtitleYXAxisDifferencePixel", 10),
            "box_tolerance_x_px": main.get("SubtitleAreaPixelToleranceXPixel", 20),
            "box_tolerance_y_px": main.get("SubtitleAreaPixelToleranceYPixel", 20),
        },
        "enhancement": {
            "mode": enhancement.get("Mode", "RealESRGAN_x2plus"),
            "enabled_models": enhancement.get("EnabledModels", "RealESRGAN_x2plus"),
            "max_long_edge": enhancement.get("MaxLongEdge", 5000),
            "denoise_enabled": enhancement.get("DenoiseEnabled", False),
            "denoise_strength": enhancement.get("DenoiseStrength", "safe"),
        },
        "low_light": {
            "mode": low_light.get("Mode", "MIRNet_LOL"),
            "enabled_models": low_light.get("EnabledModels", "MIRNet_LOL"),
            "max_long_edge": low_light.get("MaxLongEdge", 2048),
        },
        "generation": {
            "mode": generation.get("Mode", "FLUX.2-klein-base-4B"),
            "enabled_models": generation.get("EnabledModels", "__none__"),
            "width": generation.get("Width", 768),
            "height": generation.get("Height", 768),
            "steps": generation.get("Steps", 4),
        },
        "object_selection": {"more_complex": object_selection.get("MoreComplex", False)},
        "models": {},
        "save_directory": main.get("SaveDirectory", ""),
    }
