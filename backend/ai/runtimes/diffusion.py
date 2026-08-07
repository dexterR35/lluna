"""Local Diffusers text-to-image runners."""

from __future__ import annotations

import inspect
import threading
import time
from typing import Callable, Optional, Protocol

import torch
from PIL import Image

from backend.tools.shared.constants import GenerateMode
from backend.tools.shared.cuda import empty_cuda_cache
from backend.tools.installers.generate import (
    catalog_info,
    cuda_ready_for_generate,
    ensure_model_installed,
    local_repo_path,
)
from backend.tools.options.generate import (
    default_step_preset_for_mode,
    resolve_guidance,
    validate_steps_for_mode,
)

ProgressCb = Optional[Callable[[int], None]]
PreviewCb = Optional[Callable[[Image.Image], None]]
CancelEvent = Optional[threading.Event]
# Roughly this many preview frames per generation, regardless of step count -
# a 4-step distilled model previews nearly every step; a 100-step run previews
# every ~12th step. Decoding costs real time, so this is deliberately sparse.
PREVIEW_FRAME_BUDGET = 8


class GenerateCancelled(Exception):
    """Raised when text-to-image is cancelled by the user."""


class GenerateCudaError(RuntimeError):
    """Raised when CUDA is missing or broken (hard block)."""


_session_cache: dict[str, "_BaseRunner"] = {}
_infer_lock = threading.RLock()
_cancel_generation = 0
_cancel_lock = threading.Lock()
_busy = False

MAX_CACHED_MODELS = 1
DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 768
MIN_START_INTERVAL_MS = 400
_last_start_monotonic = 0.0


def cancel_generate() -> None:
    global _cancel_generation
    with _cancel_lock:
        _cancel_generation += 1


def is_generate_busy() -> bool:
    return _busy


def cached_model_count() -> int:
    return len(_session_cache)


def release_generate_models(blocking: bool = True, timeout: float = 8.0) -> bool:
    got = _infer_lock.acquire(blocking=blocking, timeout=timeout if blocking else 0)
    if not got:
        return False
    try:
        _clear_session_cache_unlocked()
        return True
    finally:
        _infer_lock.release()


def _clear_session_cache_unlocked() -> None:
    for key in list(_session_cache.keys()):
        runner = _session_cache.pop(key, None)
        if runner is not None:
            runner.dispose()
    empty_cuda_cache()


def _check_cancel(cancel_event: CancelEvent, generation: int) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise GenerateCancelled()
    with _cancel_lock:
        if generation != _cancel_generation:
            raise GenerateCancelled()


def _import_diffusers_class(name: str):
    try:
        import diffusers

        return getattr(diffusers, name)
    except (ImportError, AttributeError) as e:
        raise RuntimeError(
            f"diffusers with {name} is required for Generate. "
            "Re-run install.py or: pip install -U 'diffusers>=0.38.0' "
            "'transformers>=5.5.0' accelerate"
        ) from e


class _BaseRunner(Protocol):
    mode: GenerateMode
    dtype: torch.dtype
    pipe: object

    def dispose(self) -> None: ...

    def generate(
        self,
        prompt: str,
        *,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        seed: Optional[int],
        negative_prompt: Optional[str],
        image: Optional[Image.Image],
        strength: Optional[float],
        progress: ProgressCb,
        cancel_event: CancelEvent,
        generation: int,
        preview: PreviewCb = None,
    ) -> Image.Image: ...


class _DiffusersRunner:
    def __init__(self, mode: GenerateMode, dtype: torch.dtype):
        self.mode = mode
        self.dtype = dtype
        self.pipe = self._load_pipeline()
        self._enable_offload()

    def _load_pipeline(self):
        raise NotImplementedError

    def _enable_offload(self) -> None:
        pipe = self.pipe
        if pipe is None:
            return
        try:
            info = catalog_info(self.mode)
            if info is not None and info.sequential_cpu_offload:
                # Very large and FP8-composite models may not fit a whole
                # transformer on the GPU at once.
                pipe.enable_sequential_cpu_offload()
            else:
                pipe.enable_model_cpu_offload()
        except Exception:
            pass

    def dispose(self) -> None:
        pipe = self.pipe
        self.pipe = None
        if pipe is None:
            return
        try:
            if hasattr(pipe, "to"):
                try:
                    pipe.to("cpu")
                except Exception:
                    pass
        finally:
            del pipe
            empty_cuda_cache()

    def _callback(
        self,
        step: int,
        steps: int,
        progress: ProgressCb,
        cancel_event: CancelEvent,
        generation: int,
        *,
        latents=None,
        preview: PreviewCb = None,
        preview_interval: int = 0,
        width: int = 0,
        height: int = 0,
    ):
        _check_cancel(cancel_event, generation)
        if progress is not None and steps > 0:
            pct = int(max(0, min(100, round((step + 1) / steps * 100))))
            progress(pct)
        if (
            preview is not None
            and latents is not None
            and preview_interval > 0
            and (step % preview_interval == 0 or step == steps - 1)
        ):
            try:
                frame = self._decode_latents_preview(latents, width, height)
            except Exception:
                # Best-effort only: preview decoding is speculative (it
                # depends on internals a given pipeline may not expose the
                # same way) and must never take down the actual generation.
                frame = None
            if frame is not None:
                try:
                    preview(frame)
                except Exception:
                    pass

    def generate(
        self,
        prompt: str,
        *,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        seed: Optional[int],
        negative_prompt: Optional[str],
        image: Optional[Image.Image],
        strength: Optional[float],
        progress: ProgressCb,
        cancel_event: CancelEvent,
        generation: int,
        preview: PreviewCb = None,
    ) -> Image.Image:
        assert self.pipe is not None

        preview_interval = max(1, steps // PREVIEW_FRAME_BUDGET) if preview else 0

        def _cb(step: int, timestep, callback_kwargs):
            self._callback(
                step,
                steps,
                progress,
                cancel_event,
                generation,
                latents=callback_kwargs.get("latents"),
                preview=preview,
                preview_interval=preview_interval,
                width=width,
                height=height,
            )
            return callback_kwargs

        gen = None
        if seed is not None:
            gen = torch.Generator(device="cuda").manual_seed(int(seed))

        kwargs = self._build_call_kwargs(
            prompt=prompt,
            width=width,
            height=height,
            steps=steps,
            guidance=guidance,
            generator=gen,
            negative_prompt=negative_prompt,
            image=image,
            strength=strength,
        )
        out = self.pipe(
            **kwargs,
            callback_on_step_end=_cb,
        )

        _check_cancel(cancel_event, generation)
        images = getattr(out, "images", None) or out
        img = images[0]
        if not isinstance(img, Image.Image):
            raise RuntimeError("Generate pipeline did not return a PIL image.")
        return img.convert("RGB")

    def _decode_latents_preview(
        self, latents: torch.Tensor, width: int, height: int
    ) -> Optional[Image.Image]:
        """Best-effort mid-generation preview frame from a partially-denoised
        latent. This is speculative: flow-matching transformer pipelines
        (the FLUX family) keep latents "packed" into a patch sequence during
        sampling and only unpack to a spatial tensor right before the final
        VAE decode, via a `_unpack_latents(latents, height, width,
        vae_scale_factor)` helper that's consistent across the diffusers
        FLUX pipeline family. If a given pipeline doesn't expose that same
        shape, this raises and the caller (`_callback`) swallows it - a
        missed preview frame, never a broken generation.
        """
        vae = getattr(self.pipe, "vae", None)
        if vae is None:
            return None
        sample = latents
        if sample.dim() == 3:
            unpack = getattr(self.pipe, "_unpack_latents", None)
            scale_factor = getattr(self.pipe, "vae_scale_factor", 8)
            if not callable(unpack):
                return None
            sample = unpack(sample, height, width, scale_factor)
        scaling = getattr(vae.config, "scaling_factor", None) or 1.0
        shifting = getattr(vae.config, "shift_factor", None) or 0.0
        with torch.no_grad():
            decoded = vae.decode((sample / scaling) + shifting, return_dict=False)[0]
        processor = getattr(self.pipe, "image_processor", None)
        if processor is not None:
            frame = processor.postprocess(decoded, output_type="pil")[0]
        else:
            frame = Image.fromarray(
                (decoded[0].float().clamp(-1, 1).add(1).mul(127.5))
                .permute(1, 2, 0)
                .byte()
                .cpu()
                .numpy()
            )
        return frame.convert("RGB")

    def _build_call_kwargs(
        self,
        *,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        generator,
        negative_prompt: Optional[str] = None,
        image: Optional[Image.Image] = None,
        strength: Optional[float] = None,
    ) -> dict:
        kwargs = {
            "prompt": prompt,
            "height": int(height),
            "width": int(width),
            "guidance_scale": float(guidance),
            "num_inference_steps": int(steps),
            "generator": generator,
        }
        # Not every Diffusers pipeline __call__ accepts these kwargs (e.g. the
        # Flux2 family has no `negative_prompt` or `strength` parameter at all),
        # so only pass through what the loaded pipeline actually declares.
        supported = set(inspect.signature(self.pipe.__call__).parameters)
        if negative_prompt and "negative_prompt" in supported:
            kwargs["negative_prompt"] = negative_prompt
        if image is not None:
            if "image" not in supported:
                raise RuntimeError(
                    f"{type(self.pipe).__name__} does not support image-to-image editing."
                )
            kwargs["image"] = image
            if "strength" in supported:
                kwargs["strength"] = float(strength if strength is not None else 0.65)
        return kwargs


class _FluxKleinRunner(_DiffusersRunner):
    def _load_pipeline(self):
        path = local_repo_path(self.mode)
        Pipeline = _import_diffusers_class("Flux2KleinPipeline")
        return Pipeline.from_pretrained(
            str(path),
            torch_dtype=self.dtype,
            local_files_only=True,
            use_safetensors=True,
        )


class _Flux2DevRunner(_DiffusersRunner):
    def _load_pipeline(self):
        path = local_repo_path(self.mode)
        Pipeline = _import_diffusers_class("Flux2Pipeline")
        return Pipeline.from_pretrained(
            str(path),
            torch_dtype=self.dtype,
            local_files_only=True,
            use_safetensors=True,
        )


class _FluxKleinFp8Runner(_DiffusersRunner):
    def _load_pipeline(self):
        path = local_repo_path(self.mode)
        info = catalog_info(self.mode)
        if info is None or not info.single_file_name:
            raise RuntimeError(f"Missing FP8 model metadata for {self.mode.value}")

        Transformer = _import_diffusers_class("Flux2Transformer2DModel")
        Pipeline = _import_diffusers_class("Flux2KleinPipeline")
        transformer = Transformer.from_single_file(
            str(path / info.single_file_name),
            config=str(path),
            subfolder="transformer",
            local_files_only=True,
            low_cpu_mem_usage=True,
        )
        return Pipeline.from_pretrained(
            str(path),
            transformer=transformer,
            torch_dtype=self.dtype,
            local_files_only=True,
            use_safetensors=True,
        )


class _QwenImageRunner(_DiffusersRunner):
    def _load_pipeline(self):
        path = local_repo_path(self.mode)
        Pipeline = _import_diffusers_class("QwenImagePipeline")
        return Pipeline.from_pretrained(
            str(path),
            torch_dtype=self.dtype,
            local_files_only=True,
            use_safetensors=True,
        )

    def _build_call_kwargs(
        self,
        *,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        generator,
        negative_prompt: Optional[str] = None,
        image: Optional[Image.Image] = None,
        strength: Optional[float] = None,
    ) -> dict:
        return {
            "prompt": prompt,
            "negative_prompt": negative_prompt or " ",
            "height": int(height),
            "width": int(width),
            "true_cfg_scale": float(guidance),
            "num_inference_steps": int(steps),
            "generator": generator,
        }


def _make_runner(mode: GenerateMode, dtype: torch.dtype) -> _BaseRunner:
    info = catalog_info(mode)
    if info is None:
        raise RuntimeError(f"Unknown Generate model '{mode.value}'")
    if info.pipeline == "flux2_klein":
        return _FluxKleinRunner(mode, dtype)
    if info.pipeline == "flux2":
        return _Flux2DevRunner(mode, dtype)
    if info.pipeline == "flux2_klein_fp8":
        return _FluxKleinFp8Runner(mode, dtype)
    if info.pipeline == "qwen_image":
        return _QwenImageRunner(mode, dtype)
    raise RuntimeError(f"Unknown Diffusers pipeline '{info.pipeline}'")


def _resolve_dtype(dtype: Optional[str]) -> torch.dtype:
    """Map a user-facing precision choice to a torch dtype.

    "auto" (and any unset/unrecognized value) keeps the existing behavior:
    prefer BF16 where the GPU supports it, else FP16. An explicit choice
    that the hardware can't actually run (BF16 on a card without native
    support) raises rather than silently substituting a different
    precision than what was selected - the same "fail clearly instead of
    guessing" rule used for the VRAM/disk preflights elsewhere in this app.
    """
    normalized = (dtype or "auto").strip().lower()
    if normalized in {"int8", "int4"}:
        raise ValueError(
            f"{normalized.upper()} quantization is only available for custom models "
            "(Add Model), not built-in FLUX/Qwen models."
        )
    if normalized == "fp32":
        return torch.float32
    if normalized == "fp16":
        return torch.float16
    if normalized == "bf16":
        if not torch.cuda.is_bf16_supported():
            raise ValueError("This GPU does not support BF16. Choose FP16 or FP32 instead.")
        return torch.bfloat16
    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


def _get_runner(mode: GenerateMode, dtype: Optional[str] = None) -> _BaseRunner:
    resolved = _resolve_dtype(dtype)
    # Keyed by (mode, dtype): switching precision for the same model must
    # load a fresh pipeline, not silently keep serving whatever precision
    # happened to be cached from an earlier run.
    key = f"{mode.value}:{resolved}"
    runner = _session_cache.get(key)
    if runner is not None:
        return runner

    while len(_session_cache) >= MAX_CACHED_MODELS:
        old_key = next(iter(_session_cache))
        old = _session_cache.pop(old_key, None)
        if old is not None:
            old.dispose()

    runner = _make_runner(mode, resolved)
    _session_cache[key] = runner
    return runner


def generate_image(
    prompt: str,
    mode: GenerateMode,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: Optional[int] = None,
    guidance: Optional[float] = None,
    seed: Optional[int] = None,
    negative_prompt: Optional[str] = None,
    image: Optional[Image.Image] = None,
    strength: Optional[float] = None,
    progress: ProgressCb = None,
    cancel_event: CancelEvent = None,
    preview: PreviewCb = None,
    dtype: Optional[str] = None,
) -> Image.Image:
    """Text-to-image. Hard-requires working CUDA. Releases other caches via worker."""
    global _busy, _last_start_monotonic

    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Prompt is empty.")
    if image is not None and not isinstance(image, Image.Image):
        raise ValueError("Image-to-image input must be a PIL image.")
    if image is not None and strength is not None and not 0.0 < float(strength) <= 1.0:
        raise ValueError("Image-to-image strength must be between 0 and 1.")
    # Validate before acquiring the inference lock so an unsupported choice
    # (e.g. BF16 requested on hardware without native support) fails fast
    # instead of blocking behind whatever job is currently running.
    _resolve_dtype(dtype)

    ok, reason = cuda_ready_for_generate()
    if not ok:
        raise GenerateCudaError(reason)

    # All supported latent image pipelines require dimensions divisible by 16.
    width = max(64, (int(width) // 16) * 16)
    height = max(64, (int(height) // 16) * 16)
    if steps is None:
        steps = default_step_preset_for_mode(mode).steps
    steps = validate_steps_for_mode(mode, steps)
    if guidance is None:
        guidance = resolve_guidance(mode)

    with _cancel_lock:
        generation = _cancel_generation

    with _infer_lock:
        now = time.monotonic()
        wait = (MIN_START_INTERVAL_MS / 1000.0) - (now - _last_start_monotonic)
        if wait > 0:
            time.sleep(wait)
        _last_start_monotonic = time.monotonic()
        _busy = True
        try:
            _check_cancel(cancel_event, generation)
            if progress:
                progress(2)
            ensure_model_installed(mode)
            _check_cancel(cancel_event, generation)
            if progress:
                progress(8)
            runner = _get_runner(mode, dtype)
            _check_cancel(cancel_event, generation)
            if progress:
                progress(12)

            def prog(v: int):
                if progress:
                    progress(12 + int(max(0, min(100, v)) * 0.85))

            return runner.generate(
                prompt,
                width=width,
                height=height,
                steps=steps,
                guidance=guidance,
                seed=seed,
                negative_prompt=(negative_prompt or "").strip() or None,
                image=image,
                strength=strength,
                progress=prog,
                cancel_event=cancel_event,
                generation=generation,
                preview=preview,
            )
        finally:
            _busy = False
