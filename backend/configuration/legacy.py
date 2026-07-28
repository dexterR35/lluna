"""Compatibility adapters for the qfluentwidgets configuration facade."""

from __future__ import annotations

from backend.configuration.models import (
    ApplicationConfiguration,
    RuntimeSettings,
    SubtitleSettings,
)


def snapshot_qt_configuration(config) -> ApplicationConfiguration:
    """Copy Qt-backed values into an immutable worker-safe snapshot."""
    return ApplicationConfiguration(
        runtime=RuntimeSettings(
            job_watchdog_seconds=float(config.jobWatchdogSec.value),
            idle_release_seconds=float(config.inferIdleReleaseSec.value),
            check_updates_on_startup=bool(config.checkUpdateOnStartup.value),
        ),
        subtitle=SubtitleSettings(
            inpaint_mode=config.inpaintMode.value.value,
            subtitle_detect_mode=config.subtitleDetectMode.value.value,
            hardware_acceleration=bool(config.hardwareAcceleration.value),
            sttn_neighbor_stride=int(config.sttnNeighborStride.value),
            sttn_reference_length=int(config.sttnReferenceLength.value),
            sttn_max_load_num=int(config.sttnMaxLoadNum.value),
            propainter_max_load_num=int(config.propainterMaxLoadNum.value),
            mask_expansion_px=int(config.subtitleAreaDeviationPixel.value),
            timeline_before_frames=int(
                config.subtitleTimelineBackwardFrameCount.value
            ),
            timeline_after_frames=int(
                config.subtitleTimelineForwardFrameCount.value
            ),
            vertical_box_tolerance_px=int(
                config.subtitleYXAxisDifferencePixel.value
            ),
            box_tolerance_x_px=int(
                config.subtitleAreaPixelToleranceXPixel.value
            ),
            box_tolerance_y_px=int(
                config.subtitleAreaPixelToleranceYPixel.value
            ),
        ),
        save_directory=str(config.saveDirectory.value),
    )
