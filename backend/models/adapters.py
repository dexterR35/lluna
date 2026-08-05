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

    def load(self, record: DynamicModelRecord) -> Any:
        raise NotImplementedError

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        raise NotImplementedError

    def unload(self, loaded: Any) -> None:
        del loaded


class DiffusersAdapter(RuntimeAdapter):
    id = "diffusers"

    def load(self, record: DynamicModelRecord) -> Any:
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
        candidates = []
        if device == "cuda":
            if torch.cuda.is_bf16_supported():
                candidates.append(("bf16", torch.bfloat16))
            candidates.append(("fp16", torch.float16))
            float8 = getattr(torch, "float8_e4m3fn", None)
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
        _dtype_name, dtype = dtype_entry
        pipeline = DiffusionPipeline.from_pretrained(
            str(record.path),
            local_files_only=True,
            torch_dtype=dtype,
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

    def load(self, record: DynamicModelRecord) -> Any:
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
        result = loaded(value)
        if progress:
            progress(100)
        return result


class BiRefNetAdapter(RuntimeAdapter):
    """Manifest-backed custom BiRefNet checkpoints use the native cut-out runtime."""

    id = "birefnet"

    def load(self, record: DynamicModelRecord) -> Any:
        # Native workflow execution owns the shared worker and loads by path.
        # Keep this adapter as a capability marker for the model platform.
        if not (record.path / "config.json").is_file():
            raise AdapterError("A BiRefNet model folder must contain config.json.")
        return str(record.path)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        raise AdapterError("Custom BiRefNet checkpoints run through the Remove Background workflow nodes.")


ADAPTERS: dict[str, RuntimeAdapter] = {
    adapter.id: adapter for adapter in (DiffusersAdapter(), TransformersAdapter(), BiRefNetAdapter())
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

    def run(self, model_id: str, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        record = DynamicModelRegistry.instance().get(model_id)
        if not record.installed or not record.enabled:
            raise AdapterError("The custom model is not installed and enabled.")
        if not record.manifest.is_configured():
            raise AdapterError("The custom model needs configuration.")
        from backend.models.runtime_profiles import runtime_status

        status = runtime_status(record.manifest)
        if not status["compatible"]:
            raise AdapterError(" ".join(status["reasons"]))
        if record.manifest.task in {"text-to-image", "image-to-image", "inpainting"}:
            from backend.models.capability_validation import validate_generation_inputs

            capability_issues = validate_generation_inputs(
                record.manifest.capabilities.to_dict(record.manifest.task), inputs
            )
            if capability_issues:
                raise AdapterError(" ".join(capability_issues))
        try:
            adapter = ADAPTERS[record.manifest.adapter]
        except KeyError as exc:
            raise AdapterError(f"No in-process adapter is available for {record.manifest.adapter}.") from exc
        with self._cache_lock:
            cached = self._cache.pop(model_id, None)
            if cached is None:
                loaded = adapter.load(record)
            else:
                _cached_adapter, loaded = cached
            self._cache[model_id] = (adapter, loaded)
            while len(self._cache) > self.cache_size:
                _old_id, (old_adapter, old_loaded) = self._cache.popitem(last=False)
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
        },
        progress=progress,
        cancel_event=cancel_event,
    )
    if not isinstance(result, Image.Image):
        raise AdapterError("The selected custom model did not return an image.")
    return result
