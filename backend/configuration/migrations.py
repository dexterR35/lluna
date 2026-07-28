"""Pure migrations from the legacy qfluentwidgets JSON shape."""

from __future__ import annotations

from typing import Any, Mapping

from backend.configuration.models import SCHEMA_VERSION


def migrate_mapping(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current schema without mutating the supplied mapping."""
    if "runtime" in raw or "subtitle" in raw:
        return {
            "schema_version": int(raw.get("schema_version", SCHEMA_VERSION)),
            "runtime": dict(raw.get("runtime", {})),
            "subtitle": dict(raw.get("subtitle", {})),
            "save_directory": raw.get("save_directory", ""),
        }

    main = raw.get("Main", {})
    infer = raw.get("Infer", {})
    sttn = raw.get("Sttn", {})
    propainter = raw.get("ProPainter", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime": {
            "job_watchdog_seconds": infer.get("JobWatchdogSec", 90),
            "idle_release_seconds": infer.get("IdleReleaseSec", 60),
            "check_updates_on_startup": main.get("CheckUpdateOnStartup", True),
        },
        "subtitle": {
            "inpaint_mode": main.get("InpaintMode", "sttn-auto"),
            "subtitle_detect_mode": main.get(
                "SubtitleDetectMode", "PP_OCRv5_SERVER"
            ),
            "hardware_acceleration": main.get("HardwareAcceleration", True),
            "sttn_neighbor_stride": sttn.get("NeighborStride", 5),
            "sttn_reference_length": sttn.get("ReferenceLength", 10),
            "sttn_max_load_num": sttn.get("MaxLoadNum", 50),
            "propainter_max_load_num": propainter.get("MaxLoadNum", 70),
            "mask_expansion_px": main.get("SubtitleAreaDeviationPixel", 10),
            "timeline_before_frames": main.get(
                "SubtitleTimelineBackwardFrameCount", 3
            ),
            "timeline_after_frames": main.get(
                "SubtitleTimelineForwardFrameCount", 3
            ),
            "vertical_box_tolerance_px": main.get(
                "SubtitleYXAxisDifferencePixel", 10
            ),
            "box_tolerance_x_px": main.get(
                "SubtitleAreaPixelToleranceXPixel", 20
            ),
            "box_tolerance_y_px": main.get(
                "SubtitleAreaPixelToleranceYPixel", 20
            ),
        },
        "save_directory": main.get("SaveDirectory", ""),
    }
