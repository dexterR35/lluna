"""Feature-specific setting schemas.

Schemas deliberately do not import UI toolkits or concrete ML frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.settings.base import ModelSettings
from backend.settings.metadata import SettingMetadata as M
from backend.settings.metadata import SettingsLevel as L

ALL = ("cpu", "cuda", "directml", "mps")
TORCH = ("cpu", "cuda", "directml", "mps")


@dataclass(frozen=True)
class GenerateSettings(ModelSettings):
    model: str = "FLUX.2-klein-4B"
    width: int = 768
    height: int = 768
    steps: int = 4
    guidance_scale: float = 3.5
    seed: int = -1
    negative_prompt: str = ""
    scheduler: str = "model-default"
    precision: str = "auto"
    cpu_offload: bool = False
    attention_slicing: bool = False
    cache_model: bool = True
    output_format: str = "png"
    output_quality: int = 95
    memory_mode: str = "balanced"

    METADATA = {
        "model": M(
            "model",
            str,
            "FLUX.2-klein-4B",
            "Model",
            "Generation model.",
            L.ADVANCED,
            compatible_backends=("cuda",),
        ),
        "width": M("width", int, 768, "Width", "Output width in pixels.", L.ADVANCED, 256, 2048),
        "height": M(
            "height", int, 768, "Height", "Output height in pixels.", L.ADVANCED, 256, 2048
        ),
        "steps": M("steps", int, 4, "Steps", "Number of denoising steps.", L.ADVANCED, 1, 100),
        "guidance_scale": M(
            "guidance_scale",
            float,
            3.5,
            "Prompt strength",
            "How strongly the prompt guides the image.",
            L.ADVANCED,
            0.0,
            30.0,
        ),
        "seed": M("seed", int, -1, "Seed", "-1 chooses a random seed.", L.ADVANCED, -1, 2**32 - 1),
        "negative_prompt": M(
            "negative_prompt", str, "", "Avoid", "Content to discourage.", L.ADVANCED
        ),
        "scheduler": M(
            "scheduler", str, "model-default", "Scheduler", "Expert sampling algorithm.", L.EXPERT
        ),
        "precision": M(
            "precision",
            str,
            "auto",
            "Precision",
            "Numeric precision override.",
            L.EXPERT,
            choices=("auto", "fp32", "fp16", "bf16"),
        ),
        "cpu_offload": M(
            "cpu_offload",
            bool,
            False,
            "CPU offload",
            "Move inactive model parts to system memory.",
            L.ADVANCED,
        ),
        "attention_slicing": M(
            "attention_slicing",
            bool,
            False,
            "Attention slicing",
            "Reduce peak memory at a speed cost.",
            L.EXPERT,
        ),
        "cache_model": M(
            "cache_model",
            bool,
            True,
            "Keep model loaded",
            "Reuse model for the next job.",
            L.EXPERT,
        ),
        "output_format": M(
            "output_format",
            str,
            "png",
            "Format",
            "Saved image format.",
            L.ADVANCED,
            choices=("png", "jpeg", "webp"),
        ),
        "output_quality": M(
            "output_quality", int, 95, "Quality", "Lossy output quality.", L.ADVANCED, 1, 100
        ),
        "memory_mode": M(
            "memory_mode",
            str,
            "balanced",
            "Memory mode",
            "Memory and speed strategy.",
            L.SIMPLE,
            choices=("fast", "balanced", "quality", "low-memory"),
        ),
    }


@dataclass(frozen=True)
class ProPainterSettings(ModelSettings):
    max_frames: int = 70
    reference_frames: int = 10
    neighbor_stride: int = 5
    batch_size: int = 1
    precision: str = "auto"
    memory_mode: str = "balanced"

    METADATA = {
        "max_frames": M(
            "max_frames",
            int,
            70,
            "Frames at once",
            "Concurrent temporal working set.",
            L.ADVANCED,
            1,
            300,
            compatible_models=("propainter",),
            compatible_backends=TORCH,
        ),
        "reference_frames": M(
            "reference_frames",
            int,
            10,
            "Reference frames",
            "Temporal references used for repair.",
            L.ADVANCED,
            1,
            100,
        ),
        "neighbor_stride": M(
            "neighbor_stride",
            int,
            5,
            "Neighbor stride",
            "Spacing between neighboring frames.",
            L.EXPERT,
            1,
            100,
        ),
        "batch_size": M(
            "batch_size", int, 1, "Batch size", "Inference batch size.", L.EXPERT, 1, 16
        ),
        "precision": M(
            "precision",
            str,
            "auto",
            "Precision",
            "Numeric precision override.",
            L.EXPERT,
            choices=("auto", "fp32", "fp16", "bf16"),
        ),
        "memory_mode": M(
            "memory_mode",
            str,
            "balanced",
            "Memory mode",
            "Memory strategy.",
            L.SIMPLE,
            choices=("fast", "balanced", "quality", "low-memory"),
        ),
    }


@dataclass(frozen=True)
class STTNSettings(ModelSettings):
    max_frames: int = 50
    reference_frames: int = 10
    neighbor_stride: int = 5
    detection_sensitivity: float = 0.5
    mask_expansion_px: int = 10
    timeline_before: int = 3
    timeline_after: int = 3
    memory_mode: str = "balanced"

    METADATA = {
        "max_frames": M(
            "max_frames", int, 50, "Frames at once", "Maximum loaded frames.", L.ADVANCED, 1, 300
        ),
        "reference_frames": M(
            "reference_frames",
            int,
            10,
            "Reference frames",
            "Temporal reference count.",
            L.ADVANCED,
            1,
            100,
        ),
        "neighbor_stride": M(
            "neighbor_stride",
            int,
            5,
            "Neighbor stride",
            "Temporal sample spacing.",
            L.EXPERT,
            1,
            100,
        ),
        "detection_sensitivity": M(
            "detection_sensitivity",
            float,
            0.5,
            "Detection sensitivity",
            "Text detector sensitivity.",
            L.ADVANCED,
            0.0,
            1.0,
        ),
        "mask_expansion_px": M(
            "mask_expansion_px",
            int,
            10,
            "Mask expansion",
            "Extra pixels around detected text.",
            L.ADVANCED,
            0,
            300,
        ),
        "timeline_before": M(
            "timeline_before",
            int,
            3,
            "Frames before",
            "Extend detection backward.",
            L.ADVANCED,
            0,
            300,
        ),
        "timeline_after": M(
            "timeline_after",
            int,
            3,
            "Frames after",
            "Extend detection forward.",
            L.ADVANCED,
            0,
            300,
        ),
        "memory_mode": M(
            "memory_mode",
            str,
            "balanced",
            "Memory mode",
            "Memory strategy.",
            L.SIMPLE,
            choices=("fast", "balanced", "quality", "low-memory"),
        ),
    }


@dataclass(frozen=True)
class LamaSettings(ModelSettings):
    mask_expansion_px: int = 10
    precision: str = "auto"
    memory_mode: str = "balanced"
    METADATA = {
        "mask_expansion_px": M(
            "mask_expansion_px", int, 10, "Mask expansion", "Extra repair area.", L.ADVANCED, 0, 300
        ),
        "precision": M(
            "precision",
            str,
            "auto",
            "Precision",
            "Numeric precision override.",
            L.EXPERT,
            choices=("auto", "fp32", "fp16", "bf16"),
        ),
        "memory_mode": M(
            "memory_mode",
            str,
            "balanced",
            "Memory mode",
            "Memory strategy.",
            L.SIMPLE,
            choices=("fast", "balanced", "quality", "low-memory"),
        ),
    }


@dataclass(frozen=True)
class UpscaleSettings(ModelSettings):
    model: str = "RealESRGAN_x2plus"
    scale_factor: int = 2
    tile_size: int = 0
    tile_overlap: int = 16
    denoise_strength: float = 0.0
    face_enhancement: bool = False
    max_long_edge: int = 5000
    precision: str = "auto"
    memory_mode: str = "balanced"
    METADATA = {
        "model": M("model", str, "RealESRGAN_x2plus", "Model", "Upscaling model.", L.ADVANCED),
        "scale_factor": M(
            "scale_factor", int, 2, "Scale", "Output enlargement factor.", L.SIMPLE, choices=(2, 4)
        ),
        "tile_size": M(
            "tile_size",
            int,
            0,
            "Tile size",
            "0 selects a safe size automatically.",
            L.EXPERT,
            0,
            2048,
        ),
        "tile_overlap": M(
            "tile_overlap",
            int,
            16,
            "Tile overlap",
            "Overlap used to hide tile seams.",
            L.EXPERT,
            0,
            256,
        ),
        "denoise_strength": M(
            "denoise_strength",
            float,
            0.0,
            "Denoise",
            "Noise reduction strength.",
            L.ADVANCED,
            0.0,
            1.0,
        ),
        "face_enhancement": M(
            "face_enhancement",
            bool,
            False,
            "Enhance faces",
            "Use an optional face restoration pass.",
            L.ADVANCED,
        ),
        "max_long_edge": M(
            "max_long_edge",
            int,
            5000,
            "Output limit",
            "Maximum output long edge.",
            L.ADVANCED,
            256,
            16000,
        ),
        "precision": M(
            "precision",
            str,
            "auto",
            "Precision",
            "Numeric precision override.",
            L.EXPERT,
            choices=("auto", "fp32", "fp16", "bf16"),
        ),
        "memory_mode": M(
            "memory_mode",
            str,
            "balanced",
            "Memory mode",
            "Memory strategy.",
            L.SIMPLE,
            choices=("fast", "balanced", "quality", "low-memory"),
        ),
    }


@dataclass(frozen=True)
class LowLightSettings(ModelSettings):
    model: str = "MIRNet_LOL"
    strength: float = 1.0
    max_long_edge: int = 2048
    preserve_color: bool = True
    noise_reduction: float = 0.0
    tile_size: int = 0
    memory_mode: str = "balanced"
    METADATA = {
        "model": M("model", str, "MIRNet_LOL", "Model", "Low-light restoration model.", L.ADVANCED),
        "strength": M(
            "strength",
            float,
            1.0,
            "Strength",
            "Blend restored and original image.",
            L.ADVANCED,
            0.0,
            1.0,
        ),
        "max_long_edge": M(
            "max_long_edge",
            int,
            2048,
            "Processing resolution",
            "Maximum working long edge.",
            L.ADVANCED,
            256,
            8192,
        ),
        "preserve_color": M(
            "preserve_color", bool, True, "Preserve color", "Limit color shifts.", L.ADVANCED
        ),
        "noise_reduction": M(
            "noise_reduction",
            float,
            0.0,
            "Noise reduction",
            "Additional denoise strength.",
            L.ADVANCED,
            0.0,
            1.0,
        ),
        "tile_size": M(
            "tile_size", int, 0, "Tile size", "0 selects a safe size.", L.EXPERT, 0, 2048
        ),
        "memory_mode": M(
            "memory_mode",
            str,
            "balanced",
            "Memory mode",
            "Memory strategy.",
            L.SIMPLE,
            choices=("fast", "balanced", "quality", "low-memory"),
        ),
    }
