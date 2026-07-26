"""Real-ESRGAN RGBA enhance - keep true upscale, cap long edge at 5000."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np
import torch
from PIL import Image

from backend.tools.constant import EnhanceMode
from backend.tools.cuda_hygiene import empty_cuda_cache
from backend.tools.cutout_edges import decontaminate_rgb_fringe
from backend.tools.enhance_models import (
    ensure_model_installed,
    native_scale,
)
from backend.tools.enhance_options import EnhanceOptions
from backend.tools.image_denoise import denoise_rgb, verify_rgb
from backend.tools.realesrgan_arch import RRDBNet
from backend.tools.vram_budget import (
    VramBudgetError,
    next_smaller_tile,
    pick_enhance_tile,
)

ProgressCb = Optional[Callable[[int], None]]
CancelEvent = Optional[threading.Event]


class EnhanceCancelled(Exception):
    """Raised when enhance is cancelled by the user."""


_session_cache: dict[str, "_RealESRGANer"] = {}
_infer_lock = threading.RLock()
_cancel_generation = 0
_cancel_lock = threading.Lock()
_busy = False

# Hard limits - keep memory bounded and cancel responsive.
MAX_CACHED_MODELS = 1
MAX_LONG_EDGE = 5000
MIN_LONG_EDGE = 64
DEFAULT_TILE = 256
# Min ms between enhance starts (backend rate limit; UI also debounces).
MIN_START_INTERVAL_MS = 400
_last_start_monotonic = 0.0


def cancel_enhance() -> None:
    """Invalidate the in-flight enhance so tile loops abort ASAP."""
    global _cancel_generation
    with _cancel_lock:
        _cancel_generation += 1


def is_enhance_busy() -> bool:
    return _busy


def cached_model_count() -> int:
    return len(_session_cache)


def release_enhance_models(blocking: bool = True, timeout: float = 8.0) -> bool:
    """
    Drop cached Real-ESRGAN weights and free GPU/CPU memory.
    Acquires the inference lock so we never dispose a model mid-forward.
    Returns True if models were released (or already empty).
    """
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
        up = _session_cache.pop(key, None)
        if up is not None:
            up.dispose()
    empty_cuda_cache()

def _max_long_edge() -> int:
    from backend.config import config

    try:
        raw = int(config.enhanceMaxLongEdge.value)
    except (TypeError, ValueError):
        raw = MAX_LONG_EDGE
    return max(MIN_LONG_EDGE, min(MAX_LONG_EDGE, raw))


def _device() -> torch.device:
    from backend.config import config
    from backend.tools.hardware_accelerator import HardwareAccelerator

    hw = HardwareAccelerator.instance()
    hw.set_enabled(bool(config.hardwareAcceleration.value))
    return hw.device


def _check_cancel(cancel_event: CancelEvent, generation: int) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise EnhanceCancelled()
    with _cancel_lock:
        if generation != _cancel_generation:
            raise EnhanceCancelled()


class _RealESRGANer:
    """Tiled Real-ESRGAN inference (RGB float 0–1 NCHW)."""

    def __init__(self, mode: EnhanceMode, device: torch.device, tile: int = DEFAULT_TILE):
        self.mode = mode
        self.scale = native_scale(mode)
        self.device = device
        self.tile = max(64, int(tile))
        self.tile_pad = 10
        self.pre_pad = 0

        model = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=self.scale,
        )
        path = ensure_model_installed(mode)
        try:
            loadnet = torch.load(str(path), map_location="cpu", weights_only=False)
        except TypeError:
            loadnet = torch.load(str(path), map_location="cpu")
        if "params_ema" in loadnet:
            keyname = "params_ema"
        elif "params" in loadnet:
            keyname = "params"
        else:
            model.load_state_dict(loadnet, strict=True)
            del loadnet
            model.eval()
            self.model = model.to(device)
            return
        model.load_state_dict(loadnet[keyname], strict=True)
        del loadnet
        model.eval()
        self.model = model.to(device)

    def dispose(self) -> None:
        model = getattr(self, "model", None)
        self.model = None
        if model is None:
            return
        try:
            model.cpu()
        except Exception:
            pass
        try:
            del model
        except Exception:
            pass

    @torch.no_grad()
    def enhance_rgb(
        self,
        img: np.ndarray,
        outscale: float,
        cancel_event: CancelEvent = None,
        generation: int = 0,
        progress: ProgressCb = None,
    ) -> np.ndarray:
        """
        img: HxWx3 RGB uint8
        outscale: final scale relative to input (may be < native scale for 5k cap)
        returns: HxWx3 RGB uint8
        """
        _check_cancel(cancel_event, generation)
        img = img.astype(np.float32) / 255.0
        h, w = img.shape[:2]

        # pre_pad so h/w divisible for pixel_unshuffle on x2
        mod_scale = None
        if self.scale == 2:
            mod_scale = 2
        elif self.scale == 1:
            mod_scale = 4
        if mod_scale is not None:
            self.mod_pad_h = 0 if h % mod_scale == 0 else (mod_scale - h % mod_scale)
            self.mod_pad_w = 0 if w % mod_scale == 0 else (mod_scale - w % mod_scale)
            img = np.pad(img, ((0, self.mod_pad_h), (0, self.mod_pad_w), (0, 0)), "reflect")
        else:
            self.mod_pad_h = 0
            self.mod_pad_w = 0

        if self.pre_pad > 0:
            img = np.pad(
                img,
                ((0, self.pre_pad), (0, self.pre_pad), (0, 0)),
                "reflect",
            )

        _check_cancel(cancel_event, generation)
        img_t = torch.from_numpy(np.transpose(img, (2, 0, 1))).float().unsqueeze(0).to(self.device)

        # Always tile so cancel can abort between tiles (avoids huge single forwards too).
        use_tile = self.tile > 0
        if use_tile:
            output = self._tile_process(
                img_t,
                cancel_event=cancel_event,
                generation=generation,
                progress=progress,
            )
        else:
            _check_cancel(cancel_event, generation)
            output = self.model(img_t)

        del img_t
        output = output.data.float().cpu().clamp_(0, 1).numpy()
        output = np.transpose(output[0], (1, 2, 0))

        # remove pads (scaled)
        scale = self.scale
        if self.mod_pad_h > 0 or self.mod_pad_w > 0:
            oh, ow = output.shape[:2]
            output = output[: oh - self.mod_pad_h * scale, : ow - self.mod_pad_w * scale, :]
        if self.pre_pad > 0:
            output = output[: -(self.pre_pad * scale), : -(self.pre_pad * scale), :]

        # adjust to requested outscale (LANCZOS via cv2)
        if abs(outscale - float(scale)) > 1e-3:
            nh = max(1, int(round(h * outscale)))
            nw = max(1, int(round(w * outscale)))
            output = cv2.resize(output, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
        else:
            # ensure exact h*scale, w*scale
            nh = max(1, int(round(h * scale)))
            nw = max(1, int(round(w * scale)))
            if output.shape[0] != nh or output.shape[1] != nw:
                output = cv2.resize(output, (nw, nh), interpolation=cv2.INTER_LANCZOS4)

        return (output * 255.0).round().astype(np.uint8)

    def _tile_process(
        self,
        img: torch.Tensor,
        cancel_event: CancelEvent = None,
        generation: int = 0,
        progress: ProgressCb = None,
    ) -> torch.Tensor:
        batch, channel, height, width = img.shape
        output_height = height * self.scale
        output_width = width * self.scale
        output_shape = (batch, channel, output_height, output_width)
        output = img.new_zeros(output_shape)

        tiles_x = (width + self.tile - 1) // self.tile
        tiles_y = (height + self.tile - 1) // self.tile
        total = max(1, tiles_x * tiles_y)
        done = 0

        try:
            for y in range(tiles_y):
                for x in range(tiles_x):
                    _check_cancel(cancel_event, generation)
                    ofs_x = x * self.tile
                    ofs_y = y * self.tile
                    input_start_x = ofs_x
                    input_end_x = min(ofs_x + self.tile, width)
                    input_start_y = ofs_y
                    input_end_y = min(ofs_y + self.tile, height)

                    input_start_x_pad = max(input_start_x - self.tile_pad, 0)
                    input_end_x_pad = min(input_end_x + self.tile_pad, width)
                    input_start_y_pad = max(input_start_y - self.tile_pad, 0)
                    input_end_y_pad = min(input_end_y + self.tile_pad, height)

                    input_tile = img[
                        :,
                        :,
                        input_start_y_pad:input_end_y_pad,
                        input_start_x_pad:input_end_x_pad,
                    ]
                    try:
                        output_tile = self.model(input_tile)
                    except RuntimeError as e:
                        # Free memory and abort cleanly on OOM instead of segfaulting later.
                        msg = str(e).lower()
                        if "out of memory" in msg or "cuda" in msg and "memory" in msg:
                            del input_tile
                            empty_cuda_cache()
                        raise

                    output_start_x = input_start_x * self.scale
                    output_end_x = input_end_x * self.scale
                    output_start_y = input_start_y * self.scale
                    output_end_y = input_end_y * self.scale

                    output_start_x_tile = (input_start_x - input_start_x_pad) * self.scale
                    output_end_x_tile = output_start_x_tile + (input_end_x - input_start_x) * self.scale
                    output_start_y_tile = (input_start_y - input_start_y_pad) * self.scale
                    output_end_y_tile = output_start_y_tile + (input_end_y - input_start_y) * self.scale

                    output[
                        :,
                        :,
                        output_start_y:output_end_y,
                        output_start_x:output_end_x,
                    ] = output_tile[
                        :,
                        :,
                        output_start_y_tile:output_end_y_tile,
                        output_start_x_tile:output_end_x_tile,
                    ]
                    del output_tile, input_tile
                    done += 1
                    if progress:
                        progress(int(100 * done / total))
        except EnhanceCancelled:
            del output
            empty_cuda_cache()
            raise
        return output


def _get_upsampler(mode: EnhanceMode, tile: int = DEFAULT_TILE) -> _RealESRGANer:
    """Return the upsampler for mode - at most MAX_CACHED_MODELS in memory."""
    device = _device()
    key = f"{mode.value}:{device}:{int(tile)}"
    cached = _session_cache.get(key)
    if (
        cached is not None
        and cached.device == device
        and cached.tile == int(tile)
        and key in _session_cache
    ):
        # Drop other keys so we never stack models.
        for other in list(_session_cache.keys()):
            if other != key:
                old = _session_cache.pop(other, None)
                if old is not None:
                    old.dispose()
        return cached

    # Drop every other / stale entry first (never stack x2 + x4).
    _clear_session_cache_unlocked()

    upsampler = _RealESRGANer(mode, device, tile=tile)
    _session_cache[key] = upsampler
    while len(_session_cache) > MAX_CACHED_MODELS:
        old_key = next(k for k in _session_cache if k != key)
        old = _session_cache.pop(old_key, None)
        if old is not None:
            old.dispose()
    return upsampler


def _validate_rgba(arr: np.ndarray) -> None:
    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ValueError("RGBA input must be HxWx4")
    if arr.dtype != np.uint8:
        raise ValueError("RGBA input must be uint8")


def _verify_rgba_out(out: np.ndarray, ow: int, oh: int) -> None:
    if out.ndim != 3 or out.shape[2] != 4:
        raise ValueError("RGBA output must be HxWx4")
    if out.shape[0] != oh or out.shape[1] != ow:
        raise ValueError("RGBA output size mismatch")
    if out.dtype != np.uint8 or not np.all(np.isfinite(out)):
        raise ValueError("RGBA output invalid")


def _preprocess_rgb(
    rgb: np.ndarray,
    alpha: np.ndarray,
    options: EnhanceOptions,
    cancel_event: CancelEvent,
    generation: int,
    progress: ProgressCb,
) -> np.ndarray:
    """Fringe cleanup + optional safe denoise before Real-ESRGAN."""
    if not options.denoise:
        return rgb

    _check_cancel(cancel_event, generation)
    if progress:
        progress(12)
    try:
        rgb = decontaminate_rgb_fringe(rgb, alpha)
    except Exception:
        pass

    _check_cancel(cancel_event, generation)
    if progress:
        progress(18)

    def denoise_prog():
        if progress:
            progress(24)

    cleaned = denoise_rgb(
        rgb,
        strength=options.denoise_strength,
        cancel_event=cancel_event,
        progress=denoise_prog,
        cancel_exc=EnhanceCancelled,
    )
    if verify_rgb(cleaned, rgb):
        return cleaned
    return rgb


def enhance_rgba(
    image: Image.Image,
    mode: EnhanceMode,
    progress: ProgressCb = None,
    cancel_event: CancelEvent = None,
    options: EnhanceOptions | None = None,
) -> Image.Image:
    """
    Upscale RGBA with Real-ESRGAN. Keeps true upscaled size (no resize-back to original).
    Output long edge never exceeds enhanceMaxLongEdge (default 5000).

    Only one enhance runs at a time. Pass cancel_event (or call cancel_enhance())
    to abort; raises EnhanceCancelled.
    """
    global _busy, _last_start_monotonic

    opts = options or EnhanceOptions()

    def _p(v: int):
        if cancel_event is not None and cancel_event.is_set():
            raise EnhanceCancelled()
        if progress:
            progress(v)

    # Serialize inference - never run two Real-ESRGAN jobs at once.
    while not _infer_lock.acquire(timeout=0.25):
        if cancel_event is not None and cancel_event.is_set():
            raise EnhanceCancelled()

    # Backend rate limit: avoid thrashing cancel→reload on rapid scale flips.
    now = time.monotonic()
    wait_s = (MIN_START_INTERVAL_MS / 1000.0) - (now - _last_start_monotonic)
    if wait_s > 0:
        end = now + wait_s
        while time.monotonic() < end:
            if cancel_event is not None and cancel_event.is_set():
                _infer_lock.release()
                raise EnhanceCancelled()
            time.sleep(min(0.05, max(0.0, end - time.monotonic())))
    _last_start_monotonic = time.monotonic()

    _busy = True
    try:
        with _cancel_lock:
            generation = _cancel_generation
        _check_cancel(cancel_event, generation)
        _p(5)
        rgba = image.convert("RGBA")
        arr = np.asarray(rgba)
        _validate_rgba(arr)
        h, w = arr.shape[:2]
        long_edge = max(h, w)
        max_edge = _max_long_edge()
        scale = float(native_scale(mode))

        # Already at/over cap: fit to max, no enlarge
        if long_edge >= max_edge:
            _p(20)
            _check_cancel(cancel_event, generation)
            if long_edge > max_edge:
                s = max_edge / float(long_edge)
                nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
                out = rgba.resize((nw, nh), Image.Resampling.LANCZOS)
            else:
                out = rgba
            _p(100)
            return out

        out_long = min(long_edge * scale, float(max_edge))
        outscale = out_long / float(long_edge)

        _p(8)
        _check_cancel(cancel_event, generation)

        rgb = arr[:, :, :3].copy()
        alpha = arr[:, :, 3].copy()

        rgb = _preprocess_rgb(
            rgb,
            alpha,
            opts,
            cancel_event,
            generation,
            _p,
        )
        _p(30)
        _check_cancel(cancel_event, generation)

        budget = pick_enhance_tile(h, w, int(scale), max_edge)
        tile = budget.tile
        upsampler = _get_upsampler(mode, tile=tile)
        _p(32)

        def tile_prog(v: int):
            # map tile 0–100 into 32–90
            _p(32 + int(max(0, min(100, v)) * 0.58))

        _p(35)
        try:
            rgb_out = upsampler.enhance_rgb(
                rgb,
                outscale=outscale,
                cancel_event=cancel_event,
                generation=generation,
                progress=tile_prog,
            )
        except RuntimeError as e:
            msg = str(e).lower()
            if "out of memory" in msg or ("cuda" in msg and "memory" in msg):
                empty_cuda_cache()
                smaller = next_smaller_tile(tile)
                if smaller is None:
                    raise VramBudgetError(
                        "GPU out of memory during enhance. Try a smaller image or x2 scale."
                    ) from e
                upsampler = _get_upsampler(mode, tile=smaller)
                rgb_out = upsampler.enhance_rgb(
                    rgb,
                    outscale=outscale,
                    cancel_event=cancel_event,
                    generation=generation,
                    progress=tile_prog,
                )
            else:
                raise
        _check_cancel(cancel_event, generation)
        _p(92)

        oh, ow = rgb_out.shape[:2]
        alpha_out = cv2.resize(alpha, (ow, oh), interpolation=cv2.INTER_LINEAR)
        out = np.dstack([rgb_out, alpha_out])
        _verify_rgba_out(out, ow, oh)
        _p(100)
        return Image.fromarray(out, "RGBA")
    except EnhanceCancelled:
        # Keep the single cached model for a coalesced restart; dialog close
        # calls release_enhance_models(). Always free tile/CUDA scratch.
        empty_cuda_cache()
        raise
    except VramBudgetError:
        empty_cuda_cache()
        raise
    finally:
        _busy = False
        _infer_lock.release()
        empty_cuda_cache()
