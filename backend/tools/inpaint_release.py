"""Explicit release / dispose for inpaint models (LAMA, STTN, ProPainter)."""

from __future__ import annotations

import gc
import threading
from typing import Optional

from backend.tools.cuda_hygiene import empty_cuda_cache

_lock = threading.RLock()
_retouch_lama = None
_retouch_lama_path: Optional[str] = None
_retouch_lama_device = None

# Optional refs if subtitle path caches models on the module (best-effort).
_video_models: list = []


def register_video_inpaint_model(obj) -> None:
    with _lock:
        if obj is not None and obj not in _video_models:
            _video_models.append(obj)


def _dispose_obj(obj) -> None:
    if obj is None:
        return
    dispose = getattr(obj, "dispose", None)
    if callable(dispose):
        try:
            dispose()
            return
        except Exception:
            pass
    model = getattr(obj, "model", None)
    if model is not None:
        try:
            if hasattr(model, "cpu"):
                model.cpu()
        except Exception:
            pass
        try:
            setattr(obj, "model", None)
        except Exception:
            pass
        try:
            del model
        except Exception:
            pass


def get_retouch_lama(model_path: Optional[str] = None):
    """Cached LamaInpaint for retouch Fill (worker process)."""
    global _retouch_lama, _retouch_lama_path, _retouch_lama_device
    from backend.configuration.service import get_settings
    from backend.inpaint.lama_inpaint import LamaInpaint
    from backend.tools.hardware_accelerator import HardwareAccelerator

    hw = HardwareAccelerator.instance()
    hw.set_enabled(bool(get_settings().subtitle.hardware_acceleration))
    device = hw.device
    path = model_path
    if not path:
        import os
        from backend.core.paths import PATHS

        path = os.path.join(PATHS.project_root, "backend", "models", "big-lama.pt")

    with _lock:
        if (
            _retouch_lama is not None
            and _retouch_lama_path == path
            and str(_retouch_lama_device) == str(device)
        ):
            return _retouch_lama
        release_retouch_lama()
        _retouch_lama = LamaInpaint(device=device, model_path=path)
        _retouch_lama_path = path
        _retouch_lama_device = device
        return _retouch_lama


def release_retouch_lama() -> None:
    global _retouch_lama, _retouch_lama_path, _retouch_lama_device
    with _lock:
        if _retouch_lama is not None:
            _dispose_obj(_retouch_lama)
            _retouch_lama = None
            _retouch_lama_path = None
            _retouch_lama_device = None
        empty_cuda_cache()


def release_video_inpaint_models() -> None:
    with _lock:
        while _video_models:
            obj = _video_models.pop()
            _dispose_obj(obj)
        empty_cuda_cache()


def release_inpaint_models() -> None:
    """Drop retouch LAMA + any registered video inpaint models."""
    release_retouch_lama()
    release_video_inpaint_models()
    gc.collect()
    empty_cuda_cache()
