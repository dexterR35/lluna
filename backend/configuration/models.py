"""Typed application settings for the Electron control plane.

The control plane owns functional settings. Renderer layout preferences live in
the Electron renderer and are intentionally not represented here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

SCHEMA_VERSION = 4
_INPAINT_MODES = {"sttn-auto", "sttn-det", "lama", "propainter", "opencv"}
_DETECT_MODES = {"PP_OCRv5_MOBILE", "PP_OCRv5_SERVER"}
_DENOISE_STRENGTHS = {"safe", "medium"}


def _bounded(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


@dataclass(frozen=True)
class RuntimeSettings:
    job_watchdog_seconds: float = 90.0
    idle_release_seconds: float = 60.0
    smart_cache_enabled: bool = True
    run_history_limit: int = 100
    check_updates_on_startup: bool = True
    soft_defaults_applied: bool = False
    hardware_acceleration: bool = True

    def __post_init__(self) -> None:
        if not 5 <= float(self.job_watchdog_seconds) <= 3600:
            raise ValueError("job_watchdog_seconds must be between 5 and 3600")
        if not 0 <= float(self.idle_release_seconds) <= 86_400:
            raise ValueError("idle_release_seconds must be between 0 and 86400")
        if not isinstance(self.smart_cache_enabled, bool):
            raise TypeError("smart_cache_enabled must be a boolean")
        _bounded("run_history_limit", self.run_history_limit, 10, 1000)
        if not isinstance(self.check_updates_on_startup, bool):
            raise TypeError("check_updates_on_startup must be a boolean")
        if not isinstance(self.soft_defaults_applied, bool):
            raise TypeError("soft_defaults_applied must be a boolean")
        if not isinstance(self.hardware_acceleration, bool):
            raise TypeError("hardware_acceleration must be a boolean")


@dataclass(frozen=True)
class SubtitleSettings:
    selection_areas: str = "0.88,0.99,0.15,0.85"
    inpaint_mode: str = "sttn-auto"
    subtitle_detect_mode: str = "PP_OCRv5_SERVER"
    sttn_neighbor_stride: int = 5
    sttn_reference_length: int = 10
    sttn_max_load_num: int = 50
    propainter_max_load_num: int = 70
    mask_expansion_px: int = 10
    area_y_axis_difference_px: int = 20
    timeline_before_frames: int = 3
    timeline_after_frames: int = 3
    vertical_box_tolerance_px: int = 10
    box_tolerance_x_px: int = 20
    box_tolerance_y_px: int = 20

    def __post_init__(self) -> None:
        _string(self.selection_areas, "selection_areas")
        if self.inpaint_mode not in _INPAINT_MODES:
            raise ValueError(f"Unsupported inpaint_mode: {self.inpaint_mode}")
        if self.subtitle_detect_mode not in _DETECT_MODES:
            raise ValueError(f"Unsupported subtitle_detect_mode: {self.subtitle_detect_mode}")
        _bounded("sttn_neighbor_stride", self.sttn_neighbor_stride, 1, 100)
        _bounded("sttn_reference_length", self.sttn_reference_length, 1, 100)
        _bounded("sttn_max_load_num", self.sttn_max_load_num, 1, 300)
        _bounded("propainter_max_load_num", self.propainter_max_load_num, 1, 300)
        _bounded("mask_expansion_px", self.mask_expansion_px, 0, 300)
        _bounded("area_y_axis_difference_px", self.area_y_axis_difference_px, 0, 300)
        _bounded("timeline_before_frames", self.timeline_before_frames, 0, 300)
        _bounded("timeline_after_frames", self.timeline_after_frames, 0, 300)
        _bounded("vertical_box_tolerance_px", self.vertical_box_tolerance_px, 0, 300)
        _bounded("box_tolerance_x_px", self.box_tolerance_x_px, 0, 300)
        _bounded("box_tolerance_y_px", self.box_tolerance_y_px, 0, 300)

    @property
    def effective_sttn_max_load_num(self) -> int:
        return max(self.sttn_max_load_num, self.sttn_neighbor_stride, self.sttn_reference_length)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "SubtitleSettings":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in values.items() if key in allowed})


@dataclass(frozen=True)
class EnhancementSettings:
    mode: str = "RealESRGAN_x2plus"
    enabled_models: str = "RealESRGAN_x2plus"
    max_long_edge: int = 5000
    denoise_enabled: bool = False
    denoise_strength: str = "safe"

    def __post_init__(self) -> None:
        _string(self.mode, "enhancement.mode")
        _string(self.enabled_models, "enhancement.enabled_models")
        _bounded("enhancement.max_long_edge", self.max_long_edge, 256, 32768)
        if not isinstance(self.denoise_enabled, bool):
            raise TypeError("enhancement.denoise_enabled must be a boolean")
        if self.denoise_strength not in _DENOISE_STRENGTHS:
            raise ValueError("enhancement.denoise_strength must be safe or medium")


@dataclass(frozen=True)
class LowLightSettings:
    mode: str = "MIRNet_LOL"
    enabled_models: str = "MIRNet_LOL"
    max_long_edge: int = 2048

    def __post_init__(self) -> None:
        _string(self.mode, "low_light.mode")
        _string(self.enabled_models, "low_light.enabled_models")
        _bounded("low_light.max_long_edge", self.max_long_edge, 256, 32768)


@dataclass(frozen=True)
class GenerationSettings:
    mode: str = "FLUX.2-klein-base-4B"
    enabled_models: str = "__none__"
    width: int = 768
    height: int = 768
    steps: int = 4

    def __post_init__(self) -> None:
        _string(self.mode, "generation.mode")
        _string(self.enabled_models, "generation.enabled_models")
        _bounded("generation.width", self.width, 64, 8192)
        _bounded("generation.height", self.height, 64, 8192)
        _bounded("generation.steps", self.steps, 1, 250)


@dataclass(frozen=True)
class ObjectSelectionSettings:
    more_complex: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.more_complex, bool):
            raise TypeError("object_selection.more_complex must be a boolean")


@dataclass(frozen=True)
class ModelPlatformSettings:
    auto_scan: bool = True
    scan_interval_seconds: int = 2
    prefer_safetensors: bool = True
    allow_remote_code: bool = False
    allow_pickle_weights: bool = False
    auto_enable_imports: bool = False

    def __post_init__(self) -> None:
        for name in (
            "auto_scan",
            "prefer_safetensors",
            "allow_remote_code",
            "allow_pickle_weights",
            "auto_enable_imports",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"models.{name} must be a boolean")
        _bounded("models.scan_interval_seconds", self.scan_interval_seconds, 1, 60)


@dataclass(frozen=True)
class ApplicationConfiguration:
    schema_version: int = SCHEMA_VERSION
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    subtitle: SubtitleSettings = field(default_factory=SubtitleSettings)
    enhancement: EnhancementSettings = field(default_factory=EnhancementSettings)
    low_light: LowLightSettings = field(default_factory=LowLightSettings)
    generation: GenerationSettings = field(default_factory=GenerationSettings)
    object_selection: ObjectSelectionSettings = field(default_factory=ObjectSelectionSettings)
    models: ModelPlatformSettings = field(default_factory=ModelPlatformSettings)
    save_directory: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported configuration schema version: {self.schema_version}")
        _string(self.save_directory, "save_directory")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "ApplicationConfiguration":
        return cls(
            schema_version=int(values.get("schema_version", SCHEMA_VERSION)),
            runtime=RuntimeSettings(**dict(values.get("runtime", {}))),
            subtitle=SubtitleSettings.from_mapping(values.get("subtitle", {})),
            enhancement=EnhancementSettings(**dict(values.get("enhancement", {}))),
            low_light=LowLightSettings(**dict(values.get("low_light", {}))),
            generation=GenerationSettings(**dict(values.get("generation", {}))),
            object_selection=ObjectSelectionSettings(**dict(values.get("object_selection", {}))),
            models=ModelPlatformSettings(
                **{
                    key: value
                    for key, value in dict(values.get("models", {})).items()
                    if key in ModelPlatformSettings.__dataclass_fields__
                }
            ),
            save_directory=str(values.get("save_directory", "")),
        )
