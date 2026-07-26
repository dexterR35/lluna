"""MIRNet low-light enhancement (PyTorch) - same-size restore, tiled for VRAM."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import numpy as np
import torch
from PIL import Image

from backend.tools.constant import LowLightMode
from backend.tools.cuda_hygiene import empty_cuda_cache
from backend.tools.low_light_models import ensure_model_installed
from backend.tools.mirnet_arch import MIRNet
from backend.tools.vram_budget import VramBudgetError

ProgressCb = Optional[Callable[[int], None]]
CancelEvent = Optional[threading.Event]


class LowLightCancelled(Exception):
    """Raised when low-light enhance is cancelled by the user."""


_session_cache: dict[str, "_MIRNetRunner"] = {}
_infer_lock = threading.RLock()
_cancel_generation = 0
_cancel_lock = threading.Lock()
_busy = False

MAX_CACHED_MODELS = 1
MAX_LONG_EDGE = 2048
MIN_LONG_EDGE = 64
DEFAULT_TILE = 256
TILE_OVERLAP = 16
# MIRNet multi-scale streams need H/W divisible by 8.
ALIGN = 8
MIN_START_INTERVAL_MS = 400
_last_start_monotonic = 0.0


def cancel_low_light() -> None:
    global _cancel_generation
    with _cancel_lock:
        _cancel_generation += 1


def is_low_light_busy() -> bool:
    return _busy


def cached_model_count() -> int:
    return len(_session_cache)


def release_low_light_models(blocking: bool = True, timeout: float = 8.0) -> bool:
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


def _max_long_edge() -> int:
    from backend.config import config

    try:
        raw = int(config.lowLightMaxLongEdge.value)
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
        raise LowLightCancelled()
    with _cancel_lock:
        if generation != _cancel_generation:
            raise LowLightCancelled()


def _load_state_dict(model: MIRNet, path) -> None:
    try:
        ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
    except TypeError:
        ckpt = torch.load(str(path), map_location="cpu")

    if isinstance(ckpt, dict):
        if "state_dict" in ckpt:
            state = ckpt["state_dict"]
        elif "model_state_dict" in ckpt:
            state = ckpt["model_state_dict"]
        elif "params" in ckpt:
            state = ckpt["params"]
        else:
            # Bare state_dict (no wrapper)
            state = ckpt
    else:
        raise RuntimeError(f"Unexpected MIRNet checkpoint type: {type(ckpt)}")

    cleaned = {}
    for k, v in state.items():
        name = k[7:] if k.startswith("module.") else k
        cleaned[name] = v
    model.load_state_dict(cleaned, strict=True)


class _MIRNetRunner:
    """Tiled MIRNet inference (RGB float 0–1 NCHW)."""

    def __init__(self, mode: LowLightMode, device: torch.device, tile: int = DEFAULT_TILE):
        self.mode = mode
        self.device = device
        self.tile = max(64, int(tile))
        self.overlap = TILE_OVERLAP

        model = MIRNet()
        path = ensure_model_installed(mode)
        _load_state_dict(model, path)
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
        cancel_event: CancelEvent = None,
        generation: int = 0,
        progress: ProgressCb = None,
    ) -> np.ndarray:
        """img: HxWx3 RGB uint8 → HxWx3 RGB uint8 (same spatial size)."""
        _check_cancel(cancel_event, generation)
        h0, w0 = img.shape[:2]
        img_f = img.astype(np.float32) / 255.0

        pad_h = (ALIGN - h0 % ALIGN) % ALIGN
        pad_w = (ALIGN - w0 % ALIGN) % ALIGN
        if pad_h or pad_w:
            img_f = np.pad(img_f, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
        h, w = img_f.shape[:2]

        tile = min(self.tile, h, w)
        # Small images: single forward
        if h <= tile and w <= tile:
            _check_cancel(cancel_event, generation)
            t = torch.from_numpy(img_f).permute(2, 0, 1).unsqueeze(0).to(self.device)
            out = self.model(t)
            out = torch.clamp(out, 0, 1)
            arr = out.squeeze(0).permute(1, 2, 0).detach().cpu().numpy()
            if progress:
                progress(100)
            return (arr[:h0, :w0] * 255.0).round().astype(np.uint8)

        # Tiled with overlap blend
        stride = max(32, tile - self.overlap)
        out = np.zeros((h, w, 3), dtype=np.float32)
        weight = np.zeros((h, w, 1), dtype=np.float32)

        ys = list(range(0, max(1, h - tile + 1), stride))
        xs = list(range(0, max(1, w - tile + 1), stride))
        if ys[-1] + tile < h:
            ys.append(h - tile)
        if xs[-1] + tile < w:
            xs.append(w - tile)
        # Deduplicate while preserving order
        ys = list(dict.fromkeys(ys))
        xs = list(dict.fromkeys(xs))
        total = max(1, len(ys) * len(xs))
        done = 0

        for y in ys:
            for x in xs:
                _check_cancel(cancel_event, generation)
                patch = img_f[y : y + tile, x : x + tile]
                ph, pw = patch.shape[:2]
                # Pad patch to ALIGN if needed (edge tiles already aligned overall)
                p_pad_h = (ALIGN - ph % ALIGN) % ALIGN
                p_pad_w = (ALIGN - pw % ALIGN) % ALIGN
                if p_pad_h or p_pad_w:
                    patch = np.pad(
                        patch, ((0, p_pad_h), (0, p_pad_w), (0, 0)), mode="reflect"
                    )
                t = (
                    torch.from_numpy(patch)
                    .permute(2, 0, 1)
                    .unsqueeze(0)
                    .to(self.device)
                )
                pred = self.model(t)
                pred = torch.clamp(pred, 0, 1)
                arr = pred.squeeze(0).permute(1, 2, 0).detach().cpu().numpy()
                arr = arr[:ph, :pw]

                # Simple distance-based blend weights
                wy = np.ones((ph, 1), dtype=np.float32)
                wx = np.ones((1, pw), dtype=np.float32)
                ov = min(self.overlap, ph // 2, pw // 2)
                if ov > 0:
                    ramp = np.linspace(0.1, 1.0, ov, dtype=np.float32)
                    wy[:ov, 0] = ramp
                    wy[-ov:, 0] = ramp[::-1]
                    wx[0, :ov] = ramp
                    wx[0, -ov:] = ramp[::-1]
                wmask = wy @ wx
                wmask = wmask[:, :, None]

                out[y : y + ph, x : x + pw] += arr * wmask
                weight[y : y + ph, x : x + pw] += wmask
                done += 1
                if progress:
                    progress(int(100 * done / total))

        weight = np.maximum(weight, 1e-6)
        out = out / weight
        return (out[:h0, :w0] * 255.0).round().astype(np.uint8)


def _get_runner(mode: LowLightMode, tile: int) -> _MIRNetRunner:
    device = _device()
    key = f"{mode.value}|{device}|{tile}"
    runner = _session_cache.get(key)
    if runner is not None:
        return runner
    while len(_session_cache) >= MAX_CACHED_MODELS:
        old_key = next(iter(_session_cache))
        old = _session_cache.pop(old_key, None)
        if old is not None:
            old.dispose()
    runner = _MIRNetRunner(mode, device, tile=tile)
    _session_cache[key] = runner
    return runner


def _pick_tile(h: int, w: int) -> int:
    """Prefer smaller tiles on CUDA when free VRAM is tight."""
    from backend.tools.hardware_accelerator import HardwareAccelerator

    candidates = (512, 384, 256, 192, 128)
    free_mb, total_mb = HardwareAccelerator.instance().get_vram_mb()
    long_edge = max(h, w)
    if total_mb <= 0:
        # CPU / unknown - keep tiles modest
        return 256 if long_edge > 1024 else min(512, long_edge)
    # Rough heuristic: MIRNet activations are heavy
    if free_mb < 2500:
        candidates = (256, 192, 128, 64)
    elif free_mb < 4500:
        candidates = (384, 256, 192, 128)
    for t in candidates:
        if t <= max(h, w) or t == candidates[-1]:
            return t
    return DEFAULT_TILE


def enhance_rgb(
    image: Image.Image,
    mode: LowLightMode,
    progress: ProgressCb = None,
    cancel_event: CancelEvent = None,
) -> Image.Image:
    """
    Low-light enhance an RGB (or RGBA) PIL image. Returns RGB/RGBA same mode family.
    Same spatial size (after optional long-edge shrink for memory).
    """
    global _busy, _last_start_monotonic

    now = time.monotonic()
    if (now - _last_start_monotonic) * 1000.0 < MIN_START_INTERVAL_MS:
        time.sleep(MIN_START_INTERVAL_MS / 1000.0)
    _last_start_monotonic = time.monotonic()

    with _cancel_lock:
        generation = _cancel_generation

    has_alpha = image.mode == "RGBA"
    rgba = image.convert("RGBA") if has_alpha else None
    rgb = image.convert("RGB")
    arr = np.asarray(rgb)

    h, w = arr.shape[:2]
    max_edge = _max_long_edge()
    scale = 1.0
    if max(h, w) > max_edge:
        scale = max_edge / float(max(h, w))
        nh, nw = max(MIN_LONG_EDGE, int(round(h * scale))), max(
            MIN_LONG_EDGE, int(round(w * scale))
        )
        rgb = rgb.resize((nw, nh), Image.Resampling.LANCZOS)
        arr = np.asarray(rgb)
        h, w = arr.shape[:2]

    tile = _pick_tile(h, w)
    if progress:
        progress(5)

    with _infer_lock:
        _busy = True
        try:
            _check_cancel(cancel_event, generation)
            if progress:
                progress(10)
            runner = _get_runner(mode, tile)
            _check_cancel(cancel_event, generation)

            def prog(v: int):
                if progress:
                    progress(10 + int(max(0, min(100, v)) * 0.85))

            out_arr = runner.enhance_rgb(
                arr,
                cancel_event=cancel_event,
                generation=generation,
                progress=prog,
            )
        finally:
            _busy = False

    out_rgb = Image.fromarray(out_arr, mode="RGB")
    if scale < 1.0:
        # Upscale back to original resolution with Lanczos (restore was at reduced size)
        out_rgb = out_rgb.resize(
            (image.size[0], image.size[1]), Image.Resampling.LANCZOS
        )

    if has_alpha and rgba is not None:
        alpha = rgba.split()[-1]
        if alpha.size != out_rgb.size:
            alpha = alpha.resize(out_rgb.size, Image.Resampling.BILINEAR)
        out = out_rgb.convert("RGBA")
        out.putalpha(alpha)
        if progress:
            progress(100)
        return out

    if progress:
        progress(100)
    return out_rgb


def preflight_low_light(h: int, w: int) -> None:
    """Refuse absurd sizes before loading weights."""
    long_edge = max(int(h), int(w))
    if long_edge > _max_long_edge() * 8:
        raise VramBudgetError(
            f"Image too large for low-light enhance ({w}×{h}). "
            f"Long edge limit is {_max_long_edge()} px (after auto-shrink)."
        )
