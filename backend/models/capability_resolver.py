"""Fail-closed model capability resolution and reviewed built-in contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.models.manifest import ModelCapabilities, ModelVariant, NumberCapability


def _io_for_task(task: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    values = {
        "text-to-image": (("prompt",), ("image",)),
        "image-to-image": (("image", "prompt"), ("image",)),
        "inpainting": (("image", "mask", "prompt"), ("image",)),
        "image-segmentation": (("image",), ("mask",)),
        "object-detection": (("image", "text"), ("boxes", "labels")),
        "image-upscaling": (("image",), ("image",)),
        "image-restoration": (("image",), ("image",)),
        "text-recognition": (("image",), ("text",)),
        "text-generation": (("prompt",), ("text",)),
        "automatic-speech-recognition": (("audio",), ("text",)),
    }
    return values.get(task, ((), ()))


def _generation_capabilities(
    *,
    provenance: str,
    steps: int,
    guidance: bool,
    guidance_default: float,
    dtypes: tuple[str, ...],
) -> ModelCapabilities:
    inputs, outputs = _io_for_task("text-to-image")
    return ModelCapabilities(
        provenance=provenance,
        tasks=("text-to-image",),
        negative_prompt=False,
        guidance=guidance,
        seed=True,
        steps=NumberCapability(float(steps), float(steps), float(steps), (float(steps),)),
        guidance_scale=(NumberCapability(guidance_default, 0.0, 20.0) if guidance else None),
        supported_widths=(512, 768, 1024),
        supported_heights=(512, 768, 1024),
        width_multiple=16,
        height_multiple=16,
        dtypes=dtypes,
        inputs=inputs,
        outputs=outputs,
    )


_REVIEWED_HF: dict[str, tuple[ModelVariant, ModelCapabilities]] = {}
for repo, variant, steps, guidance, guidance_default, dtypes in (
    ("black-forest-labs/FLUX.2-klein-4B", "distilled", 4, False, 1.0, ("bf16", "fp16")),
    ("black-forest-labs/FLUX.2-klein-9B", "distilled", 4, False, 1.0, ("bf16", "fp16")),
    ("black-forest-labs/FLUX.2-klein-base-4B", "base", 50, True, 4.0, ("bf16", "fp16")),
    ("black-forest-labs/FLUX.2-klein-base-9B", "base", 50, True, 4.0, ("bf16", "fp16")),
    ("black-forest-labs/FLUX.2-dev", "base", 50, True, 4.0, ("bf16", "fp16")),
    ("black-forest-labs/FLUX.2-klein-9b-fp8", "quantized", 4, False, 1.0, ("fp8",)),
    ("Qwen/Qwen-Image", "base", 50, True, 4.0, ("bf16", "fp16")),
):
    _REVIEWED_HF[repo.lower()] = (
        ModelVariant(
            kind=variant,
            base_model=("black-forest-labs/FLUX.2-klein-9B" if "fp8" in repo.lower() else ""),
            quantization=("fp8" if "fp8" in repo.lower() else ""),
        ),
        _generation_capabilities(
            provenance="reviewed-catalog",
            steps=steps,
            guidance=guidance,
            guidance_default=guidance_default,
            dtypes=dtypes,
        ),
    )


def reviewed_huggingface_contract(repo_id: str) -> tuple[ModelVariant, ModelCapabilities] | None:
    return _REVIEWED_HF.get(repo_id.lower())


def builtin_contract(model_id: str) -> tuple[ModelVariant, ModelCapabilities]:
    if model_id.startswith("generate:"):
        value = model_id.removeprefix("generate:")
        repo_by_value = {
            "FLUX.2-klein-4B": "black-forest-labs/FLUX.2-klein-4B",
            "FLUX.2-klein-9B": "black-forest-labs/FLUX.2-klein-9B",
            "FLUX.2-klein-base-4B": "black-forest-labs/FLUX.2-klein-base-4B",
            "FLUX.2-klein-base-9B": "black-forest-labs/FLUX.2-klein-base-9B",
            "FLUX.2-dev": "black-forest-labs/FLUX.2-dev",
            "FLUX.2-klein-9b-fp8": "black-forest-labs/FLUX.2-klein-9b-fp8",
            "Qwen-Image": "Qwen/Qwen-Image",
        }
        reviewed = reviewed_huggingface_contract(repo_by_value.get(value, ""))
        if reviewed:
            return reviewed
    if model_id.startswith("bg-remove:"):
        inputs, outputs = _io_for_task("image-segmentation")
        return ModelVariant("base"), ModelCapabilities(
            provenance="reviewed-catalog",
            tasks=("image-segmentation",),
            inputs=inputs,
            outputs=outputs,
            dtypes=("fp32",),
        )
    if model_id in {"realesrgan-x2", "realesrgan-x4"}:
        inputs, outputs = _io_for_task("image-upscaling")
        scale = 2 if model_id.endswith("x2") else 4
        return ModelVariant("upscaler"), ModelCapabilities(
            provenance="reviewed-catalog",
            tasks=("image-upscaling",),
            inputs=inputs,
            outputs=outputs,
            dtypes=("fp32", "fp16"),
            scales=(scale,),
        )
    if model_id == "supir":
        inputs, outputs = _io_for_task("image-upscaling")
        return ModelVariant("upscaler", architecture="SUPIRModel"), ModelCapabilities(
            provenance="reviewed-catalog",
            tasks=("image-upscaling", "image-restoration"),
            negative_prompt=True,
            guidance=True,
            seed=True,
            steps=NumberCapability(50, 1, 200),
            guidance_scale=NumberCapability(4.0, 1.0, 15.0),
            inputs=inputs,
            outputs=outputs,
            dtypes=("fp16", "bf16", "fp32"),
            scales=tuple(range(1, 9)),
            tile_size=NumberCapability(512, 128, 1024),
        )
    task = (
        "image-restoration"
        if model_id == "mirnet"
        else "image-segmentation"
        if model_id == "sam2"
        else "object-detection"
        if model_id == "grounding-dino"
        else "text-recognition"
        if model_id.startswith("paddleocr")
        else "inpainting"
    )
    inputs, outputs = _io_for_task(task)
    return ModelVariant("base"), ModelCapabilities(
        provenance="reviewed-catalog",
        tasks=(task,),
        inputs=inputs,
        outputs=outputs,
        dtypes=("fp32", "fp16") if task != "text-recognition" else ("fp32",),
        **(
            {
                "negative_prompt": False,
                "guidance": False,
                "seed": False,
                "steps": NumberCapability(1, 1, 1, (1,)),
                "supported_widths": (),
                "supported_heights": (),
                "width_multiple": 1,
                "height_multiple": 1,
                "denoise_strength": NumberCapability(1.0, 0.0, 1.0),
            }
            if task == "inpainting"
            else {}
        ),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def inspect_local_contract(
    path: Path,
    *,
    task: str,
    adapter: str,
) -> tuple[ModelVariant, ModelCapabilities]:
    """Inspect declarative JSON only; model modules and weights are never loaded."""
    root = path if path.is_dir() else path.parent
    configs = [
        _read_json(root / relative)
        for relative in ("model_index.json", "config.json", "transformer/config.json")
        if (root / relative).is_file()
    ]
    combined: dict[str, Any] = {}
    for config in configs:
        combined.update(config)
    architecture = str(
        combined.get("_class_name") or (combined.get("architectures") or [""])[0] or ""
    )
    inputs, outputs = _io_for_task(task)
    dtype = str(combined.get("torch_dtype") or combined.get("dtype") or "").lower()
    explicit_steps = combined.get(
        "default_num_inference_steps", combined.get("num_inference_steps")
    )
    steps = None
    if isinstance(explicit_steps, (int, float)) and not isinstance(explicit_steps, bool):
        steps = NumberCapability(
            float(explicit_steps),
            float(explicit_steps),
            float(explicit_steps),
            (float(explicit_steps),),
        )
    guidance_value = combined.get("guidance_embeds")
    guidance = guidance_value if isinstance(guidance_value, bool) else None
    variant = ModelVariant(
        kind="inpainting" if task == "inpainting" else "unknown",
        architecture=architecture,
    )
    return variant, ModelCapabilities(
        provenance="local-inspection",
        tasks=(task,) if task != "custom" else (),
        negative_prompt=None,
        guidance=guidance,
        seed=True if adapter == "diffusers" else None,
        steps=steps,
        dtypes=(dtype,) if dtype else (),
        inputs=inputs,
        outputs=outputs,
    )


def huggingface_metadata_contract(
    *,
    task: str,
    adapter: str,
    tags: Iterable[str],
    base_model: str,
    configs: Iterable[Mapping[str, Any]],
) -> tuple[ModelVariant, ModelCapabilities]:
    normalized_tags = {str(tag).strip().lower() for tag in tags}
    combined: dict[str, Any] = {}
    for config in configs:
        combined.update(dict(config))
    explicit_variants = [
        value
        for value in ("distilled", "lora", "controlnet", "inpainting", "upscaler", "finetune")
        if value in normalized_tags or f"variant:{value}" in normalized_tags
    ]
    quantization = next(
        (
            value
            for value in ("fp8", "int8", "int4", "gptq", "awq", "bnb")
            if value in normalized_tags
        ),
        "",
    )
    kind = (
        "quantized"
        if quantization
        else explicit_variants[0]
        if len(explicit_variants) == 1
        else "unknown"
    )
    architecture = str(
        combined.get("_class_name") or (combined.get("architectures") or [""])[0] or ""
    )
    inputs, outputs = _io_for_task(task)
    explicit_steps = combined.get(
        "default_num_inference_steps", combined.get("num_inference_steps")
    )
    steps = None
    if isinstance(explicit_steps, (int, float)) and not isinstance(explicit_steps, bool):
        steps = NumberCapability(
            float(explicit_steps),
            float(explicit_steps),
            float(explicit_steps),
            (float(explicit_steps),),
        )
    guidance_value = combined.get("guidance_embeds")
    guidance = guidance_value if isinstance(guidance_value, bool) else None
    dtype = str(combined.get("torch_dtype") or combined.get("dtype") or quantization).lower()
    return ModelVariant(kind, base_model, quantization, architecture), ModelCapabilities(
        provenance="huggingface-metadata",
        tasks=(task,) if task != "custom" else (),
        negative_prompt=None,
        guidance=guidance,
        seed=True if adapter == "diffusers" else None,
        steps=steps,
        dtypes=(dtype,) if dtype else (),
        inputs=inputs,
        outputs=outputs,
    )
