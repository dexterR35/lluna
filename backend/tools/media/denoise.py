"""Safe RGB denoise before Real-ESRGAN (OpenCV NlMeans, no generative restore)."""

from __future__ import annotations

import threading
from typing import Callable, Optional

import cv2
import numpy as np

from backend.tools.shared.constants import DenoiseStrength

CancelEvent = Optional[threading.Event]
ProgressCb = Optional[Callable[[], None]]

# Laplacian variance below this → image treated as already clean (skip denoise).
SKIP_CLEAN_VARIANCE = 35.0

_STRENGTH_PARAMS = {
    DenoiseStrength.SAFE: {"h": 3, "hColor": 3, "blend": 0.45},
    DenoiseStrength.MEDIUM: {"h": 5, "hColor": 5, "blend": 0.62},
}


def estimate_noise_variance(gray: np.ndarray) -> float:
    """Higher values suggest more high-frequency noise."""
    gray_f = np.asarray(gray, dtype=np.float64)
    lap = cv2.Laplacian(gray_f, cv2.CV_64F)
    return float(lap.var())


def verify_rgb(rgb: np.ndarray, reference: np.ndarray) -> bool:
    """Return True when rgb is a valid replacement for reference shape."""
    if rgb is None or reference is None:
        return False
    if rgb.shape != reference.shape or rgb.dtype != np.uint8:
        return False
    if not np.all(np.isfinite(rgb)):
        return False
    return True


def _check_cancel(cancel_event: CancelEvent, cancel_exc: type[BaseException] | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        if cancel_exc is not None:
            raise cancel_exc()
        return


def denoise_rgb(
    rgb: np.ndarray,
    strength: DenoiseStrength = DenoiseStrength.SAFE,
    cancel_event: CancelEvent = None,
    progress: ProgressCb = None,
    cancel_exc: type[BaseException] | None = None,
) -> np.ndarray:
    """
    Fidelity-first denoise at native resolution. Fail closed: returns input rgb
    on skip, cancel, or verify failure.

    rgb: HxWx3 uint8
    """
    _check_cancel(cancel_event, cancel_exc)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        return rgb
    src = np.ascontiguousarray(rgb.astype(np.uint8))
    gray = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY)
    if estimate_noise_variance(gray) < SKIP_CLEAN_VARIANCE:
        return src

    params = _STRENGTH_PARAMS.get(strength, _STRENGTH_PARAMS[DenoiseStrength.SAFE])
    _check_cancel(cancel_event, cancel_exc)
    if progress:
        progress()

    denoised = cv2.fastNlMeansDenoisingColored(
        src,
        None,
        h=float(params["h"]),
        hColor=float(params["hColor"]),
        templateWindowSize=7,
        searchWindowSize=21,
    )
    _check_cancel(cancel_event, cancel_exc)

    blend = float(params["blend"])
    out = (
        blend * denoised.astype(np.float32)
        + (1.0 - blend) * src.astype(np.float32)
    ).round().astype(np.uint8)

    if not verify_rgb(out, src):
        return src
    return out
