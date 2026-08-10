"""Curated runtime profiles and compatibility checks for model adapters."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from backend.core.paths import PATHS, AppPaths
from backend.hardware.detector import get_hardware_profile
from backend.hardware.policy import select_execution_policy
from backend.models.reference.manifest import ModelManifest


# Installed memory always reports slightly below its nominal size: firmware and the
# integrated display reserve part of system RAM, and a "24 GB" card reports 24564 MB,
# not 24576. Requirements are written as round nominal figures, so comparing them
# strictly would reject exactly the hardware they were written for.
INSTALLED_MEMORY_TOLERANCE = 0.95


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
            "lluna-native",
            "Lluna native",
            "lluna-native",
            (),
            (),
            ("cpu", "cuda", "directml", "mps"),
            description="Built-in Lluna inference code.",
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
            (),
            (),
            ("cpu", "cuda", "mps"),
            isolated=True,
            description=(
                "Official BiRefNet image/video segmentation and matting runtime, "
                "in its own isolated Python environment (trust_remote_code runs "
                "out of process)."
            ),
        ),
        RuntimeProfile(
            "onnx-runtime",
            "ONNX Runtime",
            "onnx",
            ("onnxruntime",),
            ("onnxruntime",),
            ("cpu", "cuda", "directml"),
            description=(
                "Portable .onnx graphs. The only runtime that reaches DirectML, "
                "and it needs no per-model Python implementation."
            ),
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
        RuntimeProfile(
            "seedvr-python",
            "SeedVR2 isolated CUDA runtime",
            "seedvr",
            (),
            (),
            ("cuda",),
            isolated=True,
            experimental=False,
            description="Official SeedVR2 Python 3.9/3.10 runtime with CUDA-only dependencies.",
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
    elif runtime.adapter != manifest.adapter and manifest.adapter != "lluna-native":
        reasons.append(
            f"The {runtime.name} runtime does not implement the {manifest.adapter} adapter."
        )
    elif backend not in runtime.backends:
        reasons.append(f"The {runtime.name} runtime does not support {backend}.")
    if backend not in manifest.hardware.backends:
        reasons.append(f"This model does not declare support for {backend}.")
    # Eligibility is judged against *installed* memory, never momentarily free
    # memory: a model does not stop being supported by this machine because a
    # browser is holding RAM or VRAM right now. Free memory is a warning here and
    # a hard check later, in the per-job preflight (backend/tools/shared/memory.py).
    if manifest.hardware.minimum_ram_mb:
        total_ram = profile.memory.total_mb
        if not total_ram:
            warnings.append("System memory could not be measured.")
        elif total_ram < manifest.hardware.minimum_ram_mb * INSTALLED_MEMORY_TOLERANCE:
            reasons.append(
                f"{manifest.hardware.minimum_ram_mb} MB RAM is required; "
                f"this machine has {total_ram:.0f} MB."
            )
        elif profile.memory.available_mb < manifest.hardware.minimum_ram_mb:
            warnings.append(
                f"Only {profile.memory.available_mb:.0f} MB of the required "
                f"{manifest.hardware.minimum_ram_mb} MB RAM is free right now; "
                "close other applications before running this model."
            )
    gpu = profile.primary_gpu
    if manifest.hardware.minimum_vram_mb:
        total_vram = gpu.total_vram_mb if gpu else 0
        free_vram = gpu.available_vram_mb if gpu else 0
        if backend == "cpu":
            reasons.append("This model requires accelerator memory.")
        elif not total_vram:
            warnings.append("Accelerator memory could not be measured.")
        elif total_vram < manifest.hardware.minimum_vram_mb * INSTALLED_MEMORY_TOLERANCE:
            reasons.append(
                f"{manifest.hardware.minimum_vram_mb} MB VRAM is required; "
                f"{gpu.model or 'this accelerator'} has {total_vram:.0f} MB."
            )
        elif free_vram and free_vram < manifest.hardware.minimum_vram_mb:
            warnings.append(
                f"Only {free_vram:.0f} MB of the required "
                f"{manifest.hardware.minimum_vram_mb} MB VRAM is free right now; "
                "close other GPU applications before running this model."
            )
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
    if manifest.adapter == "diffusers" and manifest.variant.kind == "controlnet":
        # Like a LoRA, a ControlNet is selected inside a generation node and
        # composed onto that node's base model (backend/models/controlnet.py).
        # It needs a control image, which a Control Map node produces.
        warnings.append(
            "Select this ControlNet inside a generation node and give it a control image."
        )
    if manifest.adapter == "diffusers" and manifest.variant.kind == "lora":
        # A LoRA is never run on its own: it is selected inside a generation node
        # and composed onto that node's base model (see backend/models/lora.py).
        # It stays "compatible" so it can be installed and enabled; whether a
        # given pairing is valid is decided when the node runs, against the base
        # the user actually chose.
        warnings.append("Select this LoRA inside a generation node; it does not run on its own.")
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
        # "compatible" answers "could this machine ever run the model", which is what
        # the install flow needs - a runtime that is merely not built yet must not
        # make a model look unsupported. "runnable" additionally requires the runtime
        # to exist right now, which is what execution and the enabled toggle need.
        # Collapsing the two lets a model be enabled and then fail on first use with
        # an import error from a missing isolated venv.
        "compatible": not reasons,
        "runnable": not reasons and installed,
        "reasons": list(reasons),
        "warnings": list(warnings),
        "packages": list(runtime.packages if runtime else manifest.runtime.packages),
        "isolated": bool(runtime and runtime.isolated),
    }
