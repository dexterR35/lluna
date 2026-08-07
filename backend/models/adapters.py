"""Safe runtime adapters for manifest-backed custom models."""

from __future__ import annotations

import inspect
import threading
from collections import OrderedDict
from typing import Any, Callable

from PIL import Image

from backend.models.dynamic_registry import DynamicModelRecord, DynamicModelRegistry

Progress = Callable[[int], None] | None
CancelEvent = threading.Event | None


class AdapterError(RuntimeError):
    pass


class RuntimeAdapter:
    id = "base"

    def load(self, record: DynamicModelRecord, *, dtype: str | None = None) -> Any:
        raise NotImplementedError

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        raise NotImplementedError

    def unload(self, loaded: Any) -> None:
        del loaded


QUANTIZED_DTYPES = {"int8", "int4"}
_QUANTIZABLE_COMPONENT_NAMES = {"transformer", "unet", "text_encoder", "text_encoder_2", "text_encoder_3"}


def _diffusers_quantizable_components(path) -> list[str]:
    """Component keys in model_index.json worth quantizing (the large sub-models)."""
    import json

    try:
        raw = json.loads((path / "model_index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, dict):
        return []
    return sorted(key for key in raw if not key.startswith("_") and key in _QUANTIZABLE_COMPONENT_NAMES)


def _bitsandbytes_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("bitsandbytes") is not None


class DiffusersAdapter(RuntimeAdapter):
    id = "diffusers"

    def load(self, record: DynamicModelRecord, *, dtype: str | None = None) -> Any:
        if record.manifest.security.trust_remote_code:
            raise AdapterError("Remote model code is disabled.")
        import torch
        from diffusers import DiffusionPipeline

        device = "cuda" if torch.cuda.is_available() else "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
        if device not in record.manifest.hardware.backends:
            raise AdapterError(
                f"This model supports {', '.join(record.manifest.hardware.backends)}, not {device}."
            )
        allowed = set(record.manifest.capabilities.dtypes)
        float8 = getattr(torch, "float8_e4m3fn", None)
        named = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}
        if float8 is not None:
            named["fp8"] = float8

        requested = (dtype or "auto").strip().lower()
        if requested in QUANTIZED_DTYPES:
            # Quantized precision is an explicit opt-in only: never picked by
            # "auto", and only available for models that declare it and run
            # on CUDA with bitsandbytes installed.
            if requested not in allowed:
                raise AdapterError(
                    f"This model only declares support for: {', '.join(sorted(allowed)) or 'none'}."
                )
            if device != "cuda":
                raise AdapterError(f"{requested.upper()} quantization requires CUDA; this model would run on {device}.")
            if not _bitsandbytes_available():
                raise AdapterError(
                    f"{requested.upper()} quantization needs the bitsandbytes package, which isn't installed."
                )
            components = _diffusers_quantizable_components(record.path)
            if not components:
                raise AdapterError(
                    "Could not find a quantizable component (transformer/unet/text_encoder) "
                    "in this model's model_index.json."
                )
            compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            try:
                from diffusers import PipelineQuantizationConfig
            except ImportError as exc:
                raise AdapterError(
                    "This diffusers version doesn't support pipeline-level quantization. Upgrade diffusers."
                ) from exc
            quant_kwargs = (
                {"load_in_8bit": True}
                if requested == "int8"
                else {"load_in_4bit": True, "bnb_4bit_quant_type": "nf4", "bnb_4bit_compute_dtype": compute_dtype}
            )
            quantization_config = PipelineQuantizationConfig(
                quant_backend=f"bitsandbytes_{requested.removeprefix('int')}bit",
                quant_kwargs=quant_kwargs,
                components_to_quantize=components,
            )
            try:
                pipeline = DiffusionPipeline.from_pretrained(
                    str(record.path),
                    local_files_only=True,
                    torch_dtype=compute_dtype,
                    quantization_config=quantization_config,
                )
            except Exception as exc:
                raise AdapterError(f"{requested.upper()} quantization failed to load: {exc}") from exc
            pipeline.to(device)
            return pipeline, device

        if requested != "auto":
            # An explicit choice is validated against what this model's
            # manifest actually declares support for, and fails clearly
            # rather than silently falling back to a different precision.
            if requested not in named:
                raise AdapterError(f"Unknown precision '{requested}'.")
            if requested not in allowed:
                raise AdapterError(
                    f"This model only declares support for: {', '.join(sorted(allowed)) or 'none'}."
                )
            if requested == "bf16" and device == "cuda" and not torch.cuda.is_bf16_supported():
                raise AdapterError("This GPU does not support BF16. Choose FP16 or FP32 instead.")
            if requested in {"bf16", "fp8"} and device != "cuda":
                raise AdapterError(f"{requested.upper()} requires CUDA; this model would run on {device}.")
            resolved_dtype = named[requested]
        else:
            candidates = []
            if device == "cuda":
                if torch.cuda.is_bf16_supported():
                    candidates.append(("bf16", torch.bfloat16))
                candidates.append(("fp16", torch.float16))
                if float8 is not None:
                    candidates.append(("fp8", float8))
            elif device == "mps":
                candidates.append(("fp16", torch.float16))
            candidates.append(("fp32", torch.float32))
            dtype_entry = next((item for item in candidates if item[0] in allowed), None)
            if dtype_entry is None:
                raise AdapterError(
                    f"No declared dtype ({', '.join(record.manifest.capabilities.dtypes)}) is supported on {device}."
                )
            _dtype_name, resolved_dtype = dtype_entry

        pipeline = DiffusionPipeline.from_pretrained(
            str(record.path),
            local_files_only=True,
            torch_dtype=resolved_dtype,
        )
        pipeline.to(device)
        return pipeline, device

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Image.Image:
        import torch

        pipeline, device = loaded
        prompt = str(inputs.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Prompt is empty.")
        steps = max(1, int(inputs.get("steps") or 20))
        seed = inputs.get("seed")
        generator = None
        if seed is not None and int(seed) >= 0:
            generator = torch.Generator(device=device).manual_seed(int(seed))

        def callback(_pipe, step, _timestep, callback_kwargs):
            if cancel_event is not None and cancel_event.is_set():
                raise AdapterError("__cancelled__")
            if progress:
                progress(min(99, int((step + 1) * 100 / steps)))
            return callback_kwargs

        parameters = inspect.signature(pipeline.__call__).parameters
        kwargs: dict[str, Any] = {"prompt": prompt}
        candidates = {
            "width": int(inputs.get("width") or 768),
            "height": int(inputs.get("height") or 768),
            "num_inference_steps": steps,
            "generator": generator,
            "guidance_scale": inputs.get("guidance"),
            "negative_prompt": inputs.get("negative_prompt"),
            "callback_on_step_end": callback,
        }
        for key, value in candidates.items():
            if key in parameters and value is not None:
                kwargs[key] = value
        # Only pass image-to-image/inpainting inputs the loaded pipeline
        # actually declares - not every custom Diffusers pipeline accepts
        # them, the same "inspect the real signature" rule diffusion.py's
        # built-in runner already applies (backend/ai/runtimes/diffusion.py).
        image = inputs.get("image")
        if image is not None:
            if "image" not in parameters:
                raise AdapterError(f"{type(pipeline).__name__} does not support image-to-image editing.")
            kwargs["image"] = image
            if "strength" in parameters and inputs.get("strength") is not None:
                kwargs["strength"] = float(inputs["strength"])
        mask_image = inputs.get("mask_image")
        if mask_image is not None:
            if "mask_image" not in parameters:
                raise AdapterError(f"{type(pipeline).__name__} does not support inpainting.")
            kwargs["mask_image"] = mask_image
        result = pipeline(**kwargs)
        images = getattr(result, "images", None)
        if not images:
            raise AdapterError("The Diffusers pipeline returned no image.")
        if progress:
            progress(100)
        return images[0]

    def unload(self, loaded: Any) -> None:
        pipeline, _device = loaded
        del pipeline
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


class TransformersAdapter(RuntimeAdapter):
    id = "transformers"

    def load(self, record: DynamicModelRecord, *, dtype: str | None = None) -> Any:
        from transformers import pipeline

        task = None if record.manifest.task == "custom" else record.manifest.task
        return pipeline(
            task=task,
            model=str(record.path),
            local_files_only=True,
            trust_remote_code=False,
        )

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        if cancel_event is not None and cancel_event.is_set():
            raise AdapterError("__cancelled__")
        value = inputs.get("input", inputs.get("prompt", inputs.get("image")))
        call_kwargs = {
            key: entry
            for key, entry in {
                "prompt": inputs.get("instruction") or None,
                "max_new_tokens": inputs.get("max_new_tokens"),
                "temperature": inputs.get("temperature"),
                "top_p": inputs.get("top_p"),
            }.items()
            if entry is not None
        }
        try:
            result = loaded(value, **call_kwargs)
        except TypeError:
            # Not every transformers pipeline accepts a conditional prompt or
            # sampling kwargs (e.g. plain unconditional captioning) - fall
            # back to the bare call rather than fail on an optional extra.
            result = loaded(value)
        if progress:
            progress(100)
        return result


class BiRefNetAdapter(RuntimeAdapter):
    """Manifest-backed custom BiRefNet checkpoints use the native cut-out runtime."""

    id = "birefnet"

    def load(self, record: DynamicModelRecord, *, dtype: str | None = None) -> Any:
        # Native workflow execution owns the shared worker and loads by path.
        # Keep this adapter as a capability marker for the model platform.
        if not (record.path / "config.json").is_file():
            raise AdapterError("A BiRefNet model folder must contain config.json.")
        return str(record.path)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        raise AdapterError("Custom BiRefNet checkpoints run through the Remove Background workflow nodes.")


class SeedVRAdapter(RuntimeAdapter):
    """Capability marker for the isolated official SeedVR2 worker."""

    id = "seedvr"

    def load(self, record: DynamicModelRecord, *, dtype: str | None = None) -> Any:
        raise AdapterError("SeedVR2 models run through the Upscale Image workflow node.")

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        raise AdapterError("SeedVR2 models run through the Upscale Image workflow node.")


ADAPTERS: dict[str, RuntimeAdapter] = {
    adapter.id: adapter
    for adapter in (DiffusersAdapter(), TransformersAdapter(), BiRefNetAdapter(), SeedVRAdapter())
}


class DynamicRuntimeManager:
    _instance: "DynamicRuntimeManager | None" = None
    _lock = threading.Lock()

    def __init__(self, *, cache_size: int = 1) -> None:
        self.cache_size = max(1, cache_size)
        self._cache: OrderedDict[str, tuple[RuntimeAdapter, Any]] = OrderedDict()
        self._cache_lock = threading.RLock()

    @classmethod
    def instance(cls) -> "DynamicRuntimeManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def run(
        self,
        model_id: str,
        inputs: dict[str, Any],
        *,
        dtype: str | None = None,
        progress: Progress = None,
        cancel_event: CancelEvent = None,
    ) -> Any:
        record = DynamicModelRegistry.instance().get(model_id)
        if not record.installed or not record.enabled:
            raise AdapterError("The custom model is not installed and enabled.")
        if not record.manifest.is_configured():
            raise AdapterError("The custom model needs configuration.")
        from backend.models.reference.runtimes import runtime_status

        status = runtime_status(record.manifest)
        if not status["compatible"]:
            raise AdapterError(" ".join(status["reasons"]))
        if record.manifest.task in {"text-to-image", "image-to-image", "inpainting"}:
            from backend.models.reference.validation import validate_generation_inputs

            capability_issues = validate_generation_inputs(
                record.manifest.capabilities.to_dict(record.manifest.task), inputs
            )
            if capability_issues:
                raise AdapterError(" ".join(capability_issues))
        try:
            adapter = ADAPTERS[record.manifest.adapter]
        except KeyError as exc:
            raise AdapterError(f"No in-process adapter is available for {record.manifest.adapter}.") from exc
        cache_key = f"{model_id}:{(dtype or 'auto').strip().lower()}"
        with self._cache_lock:
            cached = self._cache.pop(cache_key, None)
            if cached is None:
                loaded = adapter.load(record, dtype=dtype)
            else:
                _cached_adapter, loaded = cached
            self._cache[cache_key] = (adapter, loaded)
            while len(self._cache) > self.cache_size:
                _old_key, (old_adapter, old_loaded) = self._cache.popitem(last=False)
                old_adapter.unload(old_loaded)
        return adapter.run(loaded, inputs, progress=progress, cancel_event=cancel_event)

    def unload_all(self) -> None:
        with self._cache_lock:
            values = tuple(self._cache.values())
            self._cache.clear()
        for adapter, loaded in values:
            adapter.unload(loaded)


def generate_with_custom_model(
    model_id: str,
    prompt: str,
    *,
    width: int,
    height: int,
    steps: int,
    seed: int | None,
    guidance: float | None = None,
    negative_prompt: str = "",
    dtype: str | None = None,
    image: Image.Image | None = None,
    strength: float | None = None,
    progress: Progress = None,
    cancel_event: CancelEvent = None,
) -> Image.Image:
    result = DynamicRuntimeManager.instance().run(
        model_id,
        {
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "seed": seed,
            **({"guidance": guidance} if guidance is not None else {}),
            **({"negative_prompt": negative_prompt} if negative_prompt else {}),
            **({"image": image, "strength": strength} if image is not None else {}),
        },
        dtype=dtype,
        progress=progress,
        cancel_event=cancel_event,
    )
    if not isinstance(result, Image.Image):
        raise AdapterError("The selected custom model did not return an image.")
    return result


def _extract_description_text(result: Any) -> str:
    """Normalize the many shapes a transformers pipeline call can return
    (a bare string, a list of dicts, a single dict) into plain text."""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            for key in ("generated_text", "text"):
                value = first.get(key)
                if isinstance(value, str):
                    return value.strip()
        if isinstance(first, str):
            return first.strip()
    if isinstance(result, dict):
        for key in ("generated_text", "text"):
            value = result.get(key)
            if isinstance(value, str):
                return value.strip()
    return ""


def describe_image_with_custom_model(
    model_id: str,
    image_path: str,
    *,
    instruction: str = "",
    temperature: float | None = None,
    top_p: float | None = None,
    max_new_tokens: int | None = None,
    progress: Progress = None,
    cancel_event: CancelEvent = None,
) -> str:
    from PIL import Image as PILImage

    with PILImage.open(image_path) as opened:
        image = opened.convert("RGB")
    result = DynamicRuntimeManager.instance().run(
        model_id,
        {
            "image": image,
            **({"instruction": instruction} if instruction else {}),
            **({"temperature": temperature} if temperature is not None else {}),
            **({"top_p": top_p} if top_p is not None else {}),
            **({"max_new_tokens": max_new_tokens} if max_new_tokens is not None else {}),
        },
        progress=progress,
        cancel_event=cancel_event,
    )
    text = _extract_description_text(result)
    if not text:
        raise AdapterError("The selected custom model did not return a text description.")
    return text
