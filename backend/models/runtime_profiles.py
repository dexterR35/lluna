"""Curated runtime profiles and compatibility checks for model adapters."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from backend.core.paths import PATHS, AppPaths
from backend.hardware.detector import get_hardware_profile
from backend.hardware.policy import select_execution_policy
from backend.models.manifest import ModelManifest


@dataclass(frozen=True)
class RuntimeProfile:
    id: str
    name: str
    adapter: str
    modules: tuple[str, ...]
    packages: tuple[str, ...]
    backends: tuple[str, ...]
    isolated: bool = False
    experimental: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "adapter": self.adapter,
            "packages": list(self.packages),
            "backends": list(self.backends),
            "isolated": self.isolated,
            "experimental": self.experimental,
            "description": self.description,
            "installed": runtime_installed(self),
        }


RUNTIME_PROFILES: dict[str, RuntimeProfile] = {
    profile.id: profile
    for profile in (
        RuntimeProfile(
            "midgard-native",
            "Midgard native",
            "midgard-native",
            (),
            (),
            ("cpu", "cuda", "directml", "mps"),
            description="Built-in Midgard inference code.",
        ),
        RuntimeProfile(
            "diffusers-torch",
            "Diffusers + PyTorch",
            "diffusers",
            ("torch", "diffusers", "transformers", "accelerate"),
            ("diffusers>=0.38.0", "transformers>=5.5.0", "accelerate>=1.0.0"),
            ("cpu", "cuda", "mps"),
            description="Curated text-to-image and image-to-image pipelines.",
        ),
        RuntimeProfile(
            "transformers-torch",
            "Transformers + PyTorch",
            "transformers",
            ("torch", "transformers"),
            ("transformers>=5.5.0",),
            ("cpu", "cuda", "mps"),
            description="Curated Transformers vision, language, and audio models.",
        ),
        RuntimeProfile(
            "birefnet-torch",
            "BiRefNet + PyTorch",
            "birefnet",
            ("torch", "torchvision", "transformers", "timm", "kornia", "einops"),
            (
                "transformers>=5.5.0",
                "timm>=1.0.0",
                "kornia>=0.7.0",
                "einops>=0.8.0",
            ),
            ("cpu", "cuda", "mps"),
            description="Official BiRefNet image/video segmentation and matting runtime.",
        ),
        RuntimeProfile(
            "paddle",
            "Paddle",
            "paddle",
            ("paddle",),
            (),
            ("cpu", "cuda"),
            description="PaddlePaddle and PaddleOCR models.",
        ),
        RuntimeProfile(
            "supir-python",
            "SUPIR isolated CUDA runtime",
            "supir",
            (),
            (),
            ("cuda",),
            isolated=True,
            experimental=False,
            description="Pinned Python 3.8–3.10 runtime for official SUPIR source.",
        ),
    )
}


def runtime_root(paths: AppPaths = PATHS) -> Path:
    return paths.data_dir / "model-runtimes"


def runtime_installed(profile: RuntimeProfile) -> bool:
    if profile.isolated:
        return (runtime_root() / profile.id / "runtime.json").is_file()
    return all(importlib.util.find_spec(module) is not None for module in profile.modules)


def get_runtime_profile(profile_id: str) -> RuntimeProfile:
    try:
        return RUNTIME_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown runtime profile: {profile_id}") from exc


def compatible_backend(manifest: ModelManifest) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Return selected backend, hard incompatibilities, and non-blocking warnings."""
    profile = get_hardware_profile()
    execution = select_execution_policy(profile)
    backend = execution.backend
    reasons: list[str] = []
    warnings: list[str] = []
    runtime = RUNTIME_PROFILES.get(manifest.runtime.profile)
    if runtime is None:
        reasons.append(f"Unknown runtime profile: {manifest.runtime.profile}")
    elif runtime.adapter != manifest.adapter and manifest.adapter != "midgard-native":
        reasons.append(
            f"The {runtime.name} runtime does not implement the {manifest.adapter} adapter."
        )
    elif backend not in runtime.backends:
        reasons.append(f"The {runtime.name} runtime does not support {backend}.")
    if backend not in manifest.hardware.backends:
        reasons.append(f"This model does not declare support for {backend}.")
    if (
        manifest.hardware.minimum_ram_mb
        and profile.memory.available_mb < manifest.hardware.minimum_ram_mb
    ):
        reasons.append(
            f"{manifest.hardware.minimum_ram_mb} MB RAM is required; "
            f"{profile.memory.available_mb:.0f} MB is available."
        )
    gpu = profile.primary_gpu
    if manifest.hardware.minimum_vram_mb:
        available_vram = gpu.available_vram_mb if gpu else 0
        if backend == "cpu":
            reasons.append("This model requires accelerator memory.")
        elif available_vram and available_vram < manifest.hardware.minimum_vram_mb:
            reasons.append(
                f"{manifest.hardware.minimum_vram_mb} MB VRAM is required; "
                f"{available_vram:.0f} MB is available."
            )
        elif not available_vram:
            warnings.append("Available accelerator memory could not be measured.")
    if (
        manifest.hardware.minimum_disk_mb
        and profile.available_disk_mb < manifest.hardware.minimum_disk_mb
    ):
        reasons.append(
            f"{manifest.hardware.minimum_disk_mb} MB disk space is required; "
            f"{profile.available_disk_mb:.0f} MB is available."
        )
    if manifest.security.trust_remote_code:
        warnings.append("This model requests remote Python code and requires explicit approval.")
    if manifest.security.allow_pickle:
        warnings.append("This model permits pickle weights; only install it from a trusted author.")
    if manifest.adapter == "diffusers" and manifest.variant.kind in {"lora", "controlnet"}:
        reasons.append(
            f"The generic Diffusers runtime cannot compose a {manifest.variant.kind} with its base model yet."
        )
    return backend, tuple(reasons), tuple(warnings)


def runtime_status(manifest: ModelManifest) -> dict:
    runtime = RUNTIME_PROFILES.get(manifest.runtime.profile)
    backend, reasons, warnings = compatible_backend(manifest)
    installed = bool(runtime and runtime_installed(runtime))
    if runtime and not installed:
        warnings = (*warnings, f"The {runtime.name} runtime is not installed.")
    return {
        "profile": manifest.runtime.profile,
        "backend": backend,
        "installed": installed,
        "compatible": not reasons,
        "reasons": list(reasons),
        "warnings": list(warnings),
        "packages": list(runtime.packages if runtime else manifest.runtime.packages),
        "isolated": bool(runtime and runtime.isolated),
    }
