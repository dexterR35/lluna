"""Typed, serializable settings shared by services and worker processes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


SCHEMA_VERSION = 1
_INPAINT_MODES = {"sttn-auto", "sttn-det", "lama", "propainter", "opencv"}
_DETECT_MODES = {"PP_OCRv5_MOBILE", "PP_OCRv5_SERVER"}


def _bounded(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True)
class RuntimeSettings:
    job_watchdog_seconds: float = 90.0
    idle_release_seconds: float = 60.0
    check_updates_on_startup: bool = True

    def __post_init__(self) -> None:
        if not 5 <= float(self.job_watchdog_seconds) <= 3600:
            raise ValueError("job_watchdog_seconds must be between 5 and 3600")
        if not 0 <= float(self.idle_release_seconds) <= 86_400:
            raise ValueError("idle_release_seconds must be between 0 and 86400")
        if not isinstance(self.check_updates_on_startup, bool):
            raise TypeError("check_updates_on_startup must be a boolean")


@dataclass(frozen=True)
class SubtitleSettings:
    inpaint_mode: str = "sttn-auto"
    subtitle_detect_mode: str = "PP_OCRv5_SERVER"
    hardware_acceleration: bool = True
    sttn_neighbor_stride: int = 5
    sttn_reference_length: int = 10
    sttn_max_load_num: int = 50
    propainter_max_load_num: int = 70
    mask_expansion_px: int = 10
    timeline_before_frames: int = 3
    timeline_after_frames: int = 3
    vertical_box_tolerance_px: int = 10
    box_tolerance_x_px: int = 20
    box_tolerance_y_px: int = 20

    def __post_init__(self) -> None:
        if self.inpaint_mode not in _INPAINT_MODES:
            raise ValueError(f"Unsupported inpaint_mode: {self.inpaint_mode}")
        if self.subtitle_detect_mode not in _DETECT_MODES:
            raise ValueError(
                f"Unsupported subtitle_detect_mode: {self.subtitle_detect_mode}"
            )
        if not isinstance(self.hardware_acceleration, bool):
            raise TypeError("hardware_acceleration must be a boolean")
        _bounded("sttn_neighbor_stride", self.sttn_neighbor_stride, 1, 100)
        _bounded("sttn_reference_length", self.sttn_reference_length, 1, 100)
        _bounded("sttn_max_load_num", self.sttn_max_load_num, 1, 300)
        _bounded("propainter_max_load_num", self.propainter_max_load_num, 1, 300)
        _bounded("mask_expansion_px", self.mask_expansion_px, 0, 300)
        _bounded("timeline_before_frames", self.timeline_before_frames, 0, 300)
        _bounded("timeline_after_frames", self.timeline_after_frames, 0, 300)
        _bounded("vertical_box_tolerance_px", self.vertical_box_tolerance_px, 0, 300)
        _bounded("box_tolerance_x_px", self.box_tolerance_x_px, 0, 300)
        _bounded("box_tolerance_y_px", self.box_tolerance_y_px, 0, 300)

    @property
    def effective_sttn_max_load_num(self) -> int:
        return max(
            self.sttn_max_load_num,
            self.sttn_neighbor_stride,
            self.sttn_reference_length,
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "SubtitleSettings":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in values.items() if key in allowed})


@dataclass(frozen=True)
class ApplicationConfiguration:
    schema_version: int = SCHEMA_VERSION
    runtime: RuntimeSettings = RuntimeSettings()
    subtitle: SubtitleSettings = SubtitleSettings()
    save_directory: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported configuration schema version: {self.schema_version}"
            )
        if not isinstance(self.save_directory, str):
            raise TypeError("save_directory must be a string")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "ApplicationConfiguration":
        return cls(
            schema_version=int(values.get("schema_version", SCHEMA_VERSION)),
            runtime=RuntimeSettings(**dict(values.get("runtime", {}))),
            subtitle=SubtitleSettings.from_mapping(values.get("subtitle", {})),
            save_directory=str(values.get("save_directory", "")),
        )
