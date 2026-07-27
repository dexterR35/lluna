"""Text-to-image runners (FLUX.2 / SDXL Turbo / SD 1.5)."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Protocol

import torch
from PIL import Image

from backend.tools.constant import GenerateMode
from backend.tools.cuda_hygiene import empty_cuda_cache
from backend.tools.generate_models import (
    catalog_info,
    cuda_ready_for_generate,
    ensure_model_installed,
    local_repo_path,
)

ProgressCb = Optional[Callable[[int], None]]
CancelEvent = Optional[threading.Event]


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
DEFAULT_STEPS = 4
DEFAULT_GUIDANCE = 1.0
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


def _import_flux_pipeline_cls():
    try:
        from diffusers import Flux2KleinPipeline

        return Flux2KleinPipeline
    except ImportError:
        pass
    try:
        from diffusers import DiffusionPipeline

        return DiffusionPipeline
    except ImportError as e:
        raise RuntimeError(
            "diffusers with Flux2KleinPipeline is required for Generate. "
            "Re-run install.py or: pip install -U 'diffusers>=0.37.1' accelerate"
        ) from e


def _import_autot2i_pipeline_cls():
    try:
        from diffusers import AutoPipelineForText2Image

        return AutoPipelineForText2Image
    except ImportError:
        return None


def _import_sd15_pipeline_cls():
    try:
        from diffusers import StableDiffusionPipeline

        return StableDiffusionPipeline
    except ImportError:
        return None


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
        progress: ProgressCb,
        cancel_event: CancelEvent,
        generation: int,
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
            # Keeps VRAM lower on consumer GPUs.
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

    def _callback(self, step: int, steps: int, progress: ProgressCb, cancel_event: CancelEvent, generation: int):
        _check_cancel(cancel_event, generation)
        if progress is not None and steps > 0:
            pct = int(max(0, min(100, round((step + 1) / steps * 100))))
            progress(pct)

    def generate(
        self,
        prompt: str,
        *,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        seed: Optional[int],
        progress: ProgressCb,
        cancel_event: CancelEvent,
        generation: int,
    ) -> Image.Image:
        assert self.pipe is not None

        def _cb(step: int, timestep, callback_kwargs):
            self._callback(step, steps, progress, cancel_event, generation)
            return callback_kwargs

        gen = None
        if seed is not None:
            gen = torch.Generator(device="cuda").manual_seed(int(seed))

        kwargs = {
            "prompt": prompt,
            "height": int(height),
            "width": int(width),
            "guidance_scale": float(guidance),
            "num_inference_steps": int(steps),
            "generator": gen,
        }
        try:
            out = self.pipe(
                **kwargs,
                callback_on_step_end=_cb,
            )
        except TypeError:
            out = self.pipe(**kwargs)

        _check_cancel(cancel_event, generation)
        images = getattr(out, "images", None) or out
        img = images[0]
        if not isinstance(img, Image.Image):
            raise RuntimeError("Generate pipeline did not return a PIL image.")
        return img.convert("RGB")


class _FluxRunner(_DiffusersRunner):
    def __init__(self, mode: GenerateMode, dtype: torch.dtype):
        super().__init__(mode, dtype)

    def _load_pipeline(self):
        path = local_repo_path(self.mode)
        Pipeline = _import_flux_pipeline_cls()
        return Pipeline.from_pretrained(
            str(path),
            torch_dtype=self.dtype,
            local_files_only=True,
        )

class _SdxlTurboRunner(_DiffusersRunner):
    def __init__(self, mode: GenerateMode, dtype: torch.dtype):
        super().__init__(mode, dtype)

    def _load_pipeline(self):
        path = local_repo_path(self.mode)
        AutoT2I = _import_autot2i_pipeline_cls()
        if AutoT2I is not None:
            return AutoT2I.from_pretrained(
                str(path),
                torch_dtype=self.dtype,
                local_files_only=True,
            )
        from diffusers import DiffusionPipeline

        return DiffusionPipeline.from_pretrained(
            str(path),
            torch_dtype=self.dtype,
            local_files_only=True,
        )


class _Sd15Runner(_DiffusersRunner):
    def __init__(self, mode: GenerateMode, dtype: torch.dtype):
        super().__init__(mode, dtype)

    def _load_pipeline(self):
        path = local_repo_path(self.mode)
        SD15 = _import_sd15_pipeline_cls()
        if SD15 is not None:
            return SD15.from_pretrained(
                str(path),
                torch_dtype=self.dtype,
                local_files_only=True,
                safety_checker=None,
            )
        from diffusers import DiffusionPipeline

        return DiffusionPipeline.from_pretrained(
            str(path),
            torch_dtype=self.dtype,
            local_files_only=True,
        )


def _make_runner(mode: GenerateMode, dtype: torch.dtype) -> _BaseRunner:
    info = catalog_info(mode)
    pipeline = info.pipeline if info is not None else "flux"
    if pipeline == "flux":
        return _FluxRunner(mode, dtype)
    if pipeline == "sdxl_turbo":
        return _SdxlTurboRunner(mode, dtype)
    if pipeline == "sd15":
        return _Sd15Runner(mode, dtype)
    raise RuntimeError(f"Unknown generate pipeline '{pipeline}' for {mode.value}")


def _get_runner(mode: GenerateMode) -> _BaseRunner:
    key = mode.value
    runner = _session_cache.get(key)
    if runner is not None:
        return runner

    while len(_session_cache) >= MAX_CACHED_MODELS:
        old_key = next(iter(_session_cache))
        old = _session_cache.pop(old_key, None)
        if old is not None:
            old.dispose()

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    runner = _make_runner(mode, dtype)
    _session_cache[key] = runner
    return runner


def generate_image(
    prompt: str,
    mode: GenerateMode,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: int = DEFAULT_STEPS,
    guidance: float = DEFAULT_GUIDANCE,
    seed: Optional[int] = None,
    progress: ProgressCb = None,
    cancel_event: CancelEvent = None,
) -> Image.Image:
    """Text-to-image. Hard-requires working CUDA. Releases other caches via worker."""
    global _busy, _last_start_monotonic

    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Prompt is empty.")

    ok, reason = cuda_ready_for_generate()
    if not ok:
        raise GenerateCudaError(reason)

    # Align to multiples of 16 (FLUX.2 klein requirement).
    width = max(64, (int(width) // 16) * 16)
    height = max(64, (int(height) // 16) * 16)
    steps = max(1, int(steps))

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
            runner = _get_runner(mode)
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
                progress=prog,
                cancel_event=cancel_event,
                generation=generation,
            )
        finally:
            _busy = False
