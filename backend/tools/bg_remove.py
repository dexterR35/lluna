"""Image-only background removal (rembg / ONNX). No video pipeline."""

from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional, Union

import numpy as np
from PIL import Image, ImageOps

from backend.tools.constant import BgRemoveMode
from backend.tools.hardware_accelerator import HardwareAccelerator

logger = logging.getLogger(__name__)

# 0 = keep original resolution (no downsample). Set >0 only as an optional safety cap.
MAX_LONG_EDGE = 0
ProgressCb = Optional[Callable[[int], None]]


class BackgroundRemover:
    """Image-only rembg session (CUDA-first when Hardware Acceleration is on)."""

    def __init__(
        self,
        mode: BgRemoveMode = BgRemoveMode.BIREFNET,
        providers: Optional[List[str]] = None,
        max_long_edge: int = MAX_LONG_EDGE,
    ):
        self.mode = mode
        self._providers = providers
        self._max_long_edge = max_long_edge
        self._session = None
        self._active_providers: List[str] = []

    @property
    def device_label(self) -> str:
        if not self._active_providers:
            return "Not initialized"
        top = self._active_providers[0]
        if top == "CUDAExecutionProvider":
            return "GPU (CUDA)"
        if top == "DmlExecutionProvider":
            return "GPU (DirectML)"
        if top in {"ROCMExecutionProvider", "MIGraphXExecutionProvider"}:
            return "GPU (ROCm)"
        if top == "CPUExecutionProvider":
            return "CPU"
        return top.replace("ExecutionProvider", "")

    def _resolve_providers(self) -> List[str]:
        if self._providers is not None:
            return list(self._providers)
        from backend.config import config

        hw = HardwareAccelerator.instance()
        hw.set_enabled(bool(config.hardwareAcceleration.value))
        return hw.get_onnx_execution_providers()

    def _ensure_session(self):
        if self._session is not None:
            return
        try:
            from rembg import new_session
        except ImportError as e:
            raise ImportError(
                'rembg is not installed. Run: pip install "rembg[cpu]"  (or re-run install.py)'
            ) from e

        providers = self._resolve_providers()
        try:
            self._session = new_session(self.mode.value, providers=providers)
        except Exception:
            if providers == ["CPUExecutionProvider"]:
                raise
            logger.warning(
                "Accelerated Remove BG session failed; retrying with CPU",
                exc_info=True,
            )
            providers = ["CPUExecutionProvider"]
            self._session = new_session(self.mode.value, providers=providers)
        try:
            self._active_providers = list(self._session.inner_session.get_providers())
        except Exception:
            self._active_providers = providers

    @staticmethod
    def load_rgb(path: str) -> Image.Image:
        """Load image as RGB with EXIF orientation applied (image-only)."""
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return im.convert("RGB")

    def _fit_long_edge(self, pil: Image.Image) -> Image.Image:
        """Optionally cap longest edge. 0 / unset = return original size unchanged."""
        if not self._max_long_edge or self._max_long_edge <= 0:
            return pil
        w, h = pil.size
        long_edge = max(w, h)
        if long_edge <= self._max_long_edge:
            return pil
        scale = self._max_long_edge / float(long_edge)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        return pil.resize((nw, nh), Image.Resampling.LANCZOS)

    @staticmethod
    def _to_pil_rgb(image: Union[str, Image.Image, np.ndarray]) -> Image.Image:
        if isinstance(image, str):
            return BackgroundRemover.load_rgb(image)
        if isinstance(image, Image.Image):
            return ImageOps.exif_transpose(image).convert("RGB")
        if isinstance(image, np.ndarray):
            arr = image
            if arr.ndim == 2:
                return Image.fromarray(arr).convert("RGB")
            if arr.shape[2] == 4:
                rgba = arr[:, :, [2, 1, 0, 3]]
                return Image.fromarray(rgba, "RGBA").convert("RGB")
            return Image.fromarray(arr[:, :, ::-1].copy(), "RGB")
        raise TypeError(f"Unsupported image type: {type(image)}")

    def remove(
        self,
        image: Union[str, Image.Image, np.ndarray],
        progress: ProgressCb = None,
        protect_mask: Union[str, np.ndarray, Image.Image, None] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> Image.Image:
        """
        Remove background from a still image. Returns RGBA (no video).

        BiRefNet cannot be conditioned on a keep-mask. When ``protect_mask`` is
        set, we take the model alpha and force-merge the protect mask into it
        (``max(model, protect)``) *before* applying cutout to the original RGB
        — so protected pixels are never made transparent.
        """
        def _p(v: int):
            if progress:
                progress(v)

        _p(10)
        self._ensure_session()
        if log is not None:
            log(f"Device: {self.device_label} | Model: {self.mode.value}")
        _p(25)
        from rembg import remove

        pil = self._fit_long_edge(self._to_pil_rgb(image))
        _p(40)
        # Mask-only so we can union protect before any cutout is applied.
        mask = remove(pil, session=self._session, only_mask=True)
        _p(70)
        if not isinstance(mask, Image.Image):
            mask = Image.fromarray(np.asarray(mask))
        mask_l = mask.convert("L")
        if protect_mask is not None:
            mask_l = merge_protect_into_mask(mask_l, protect_mask, log=log)
        _p(85)
        out = pil.convert("RGBA")
        out.putalpha(mask_l)
        _p(95)
        return out

    def process_to_file(
        self,
        input_path: str,
        output_path: str,
        progress: ProgressCb = None,
        protect_mask_path: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Image-only: remove BG and write transparent PNG."""
        def _p(v: int):
            if progress:
                progress(v)

        result = self.remove(
            input_path,
            progress=progress,
            protect_mask=protect_mask_path,
            log=log,
        )
        if protect_mask_path:
            _p(97)
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        result.save(output_path, format="PNG", optimize=True)
        _p(100)
        return output_path


def _load_mask_l(
    mask: Union[str, np.ndarray, Image.Image],
    size: tuple[int, int],
) -> Image.Image:
    if isinstance(mask, str):
        with Image.open(mask) as im:
            mask_l = im.convert("L")
    elif isinstance(mask, Image.Image):
        mask_l = mask.convert("L")
    else:
        m = np.asarray(mask)
        if m.ndim != 2:
            raise ValueError("protect mask must be 2D")
        mask_l = Image.fromarray(m.astype(np.uint8), mode="L")
    if mask_l.size != size:
        mask_l = mask_l.resize(size, Image.Resampling.BILINEAR)
    return mask_l


def merge_protect_into_mask(
    model_mask: Image.Image,
    protect: Union[str, np.ndarray, Image.Image],
    log: Optional[Callable[[str], None]] = None,
) -> Image.Image:
    """
    Force-keep painted regions in the cutout alpha.

    BiRefNet has no protect input — we union the keep-mask into the model
    mask so protected pixels stay opaque when alpha is applied to the photo.
    Any deliberately marked keep pixel is forced fully opaque. This makes the
    protect contract deterministic even when the editor brush has soft edges.
    """
    base = model_mask.convert("L")
    w, h = base.size
    keep = _load_mask_l(protect, (w, h))
    model_a = np.asarray(base, dtype=np.uint8)
    keep_a = np.asarray(keep, dtype=np.uint8)
    keep_binary = keep_a > 0
    if not np.any(keep_binary):
        return base
    merged = model_a.copy()
    merged[keep_binary] = 255
    if log is not None:
        pixels = int(np.count_nonzero(keep_binary))
        forced = int(np.count_nonzero(keep_binary & (model_a < 255)))
        log(
            f"Protect mask: {pixels:,} px marked keep, "
            f"{forced:,} px forced opaque over model cut ({w}x{h})"
        )
    return Image.fromarray(merged, mode="L")


def apply_protect_mask(
    rgba: Image.Image,
    mask: Union[str, np.ndarray, Image.Image],
    source: Union[str, Image.Image, np.ndarray, None] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Image.Image:
    """
    Legacy helper: raise alpha (and optionally restore RGB) for keep regions.

    Prefer ``merge_protect_into_mask`` before cutout; this remains for callers
    that already have an RGBA cutout.
    """
    out = rgba.convert("RGBA")
    arr = np.asarray(out).copy()
    h, w = arr.shape[:2]
    keep_img = _load_mask_l(mask, (w, h))
    keep = np.asarray(keep_img, dtype=np.uint8) > 0
    if not np.any(keep):
        return out
    strength = keep.astype(np.float32)
    if source is not None:
        src_pil = BackgroundRemover._to_pil_rgb(source)
        if src_pil.size != (w, h):
            src_pil = src_pil.resize((w, h), Image.Resampling.LANCZOS)
        src_rgb = np.asarray(src_pil, dtype=np.float32)
        s3 = strength[..., np.newaxis]
        rgb = arr[:, :, :3].astype(np.float32)
        arr[:, :, :3] = np.clip(rgb * (1.0 - s3) + src_rgb * s3, 0.0, 255.0).astype(
            np.uint8
        )

    alpha = arr[:, :, 3].astype(np.float32)
    arr[:, :, 3] = np.clip(alpha + (255.0 - alpha) * strength, 0.0, 255.0).astype(
        np.uint8
    )
    if log is not None:
        pixels = int(np.count_nonzero(keep))
        log(f"Protect mask applied: {pixels:,} px kept from original ({w}x{h})")
    return Image.fromarray(arr, "RGBA")


_session_cache: dict[str, BackgroundRemover] = {}


def release_bg_sessions() -> None:
    """Drop cached rembg sessions and free GPU/ORT memory."""
    global _session_cache
    for key in list(_session_cache.keys()):
        remover = _session_cache.pop(key, None)
        if remover is None:
            continue
        session = getattr(remover, "_session", None)
        remover._session = None
        if session is not None:
            try:
                del session
            except Exception:
                pass
    _session_cache.clear()
    try:
        from backend.tools.cuda_hygiene import empty_cuda_cache

        empty_cuda_cache()
    except Exception:
        pass


def get_bg_remover(mode: Optional[BgRemoveMode] = None) -> BackgroundRemover:
    """Reuse sessions per model + provider set."""
    from backend.config import config

    if mode is None:
        mode = config.bgRemoveMode.value

    hw = HardwareAccelerator.instance()
    hw.set_enabled(bool(config.hardwareAcceleration.value))
    providers = hw.get_onnx_execution_providers()
    key = f"{mode.value}|{','.join(providers)}"

    if key not in _session_cache:
        _session_cache[key] = BackgroundRemover(mode, providers=providers)
    return _session_cache[key]


def run_bg_remove_job(
    input_path: str,
    output_path: str,
    mode: Optional[BgRemoveMode] = None,
    progress: ProgressCb = None,
    log: Optional[Callable[[str], None]] = None,
    protect_mask_path: Optional[str] = None,
) -> str:
    """
    Standalone image-only job entry (safe for a child process).
    No video I/O, no SubtitleRemover.
    """
    remover = get_bg_remover(mode)
    if log:
        if protect_mask_path:
            log(
                "Protect mask: force-keep painted areas in cutout "
                "(model cannot see the mask; we union it into alpha)"
            )
    return remover.process_to_file(
        input_path,
        output_path,
        progress=progress,
        protect_mask_path=protect_mask_path,
        log=log,
    )
