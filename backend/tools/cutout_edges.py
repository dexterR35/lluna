"""Alpha-aware RGB fringe cleanup for product cutouts (alpha never modified)."""

from __future__ import annotations

import cv2
import numpy as np

# Soft matte band where background color often bleeds into RGB.
FRINGE_ALPHA_MIN = 8
FRINGE_ALPHA_MAX = 247
OPAQUE_ALPHA = 250
# Max blend toward foreground color estimate at fringe pixels.
FRINGE_BLEND = 0.65


def decontaminate_rgb_fringe(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """
    Pull edge RGB toward nearby opaque foreground color so Real-ESRGAN does not
    amplify background spill. Alpha is read-only input; never modified here.

    rgb: HxWx3 uint8
    alpha: HxW uint8
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be HxWx3")
    if alpha.shape[:2] != rgb.shape[:2]:
        raise ValueError("alpha shape must match rgb spatial size")
    if rgb.dtype != np.uint8 or alpha.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        alpha = np.clip(alpha, 0, 255).astype(np.uint8)

    fringe = (alpha >= FRINGE_ALPHA_MIN) & (alpha <= FRINGE_ALPHA_MAX)
    if not np.any(fringe):
        return rgb

    opaque = (alpha >= OPAQUE_ALPHA).astype(np.float32)
    if float(opaque.sum()) < 1.0:
        return rgb

    rgb_f = rgb.astype(np.float32)
    fg = np.empty_like(rgb_f)
    ksize = 5
    sigma = 1.2
    for c in range(3):
        num = cv2.GaussianBlur(rgb_f[:, :, c] * opaque, (ksize, ksize), sigma)
        den = cv2.GaussianBlur(opaque, (ksize, ksize), sigma) + 1e-6
        fg[:, :, c] = num / den

    blend = fringe.astype(np.float32) * FRINGE_BLEND
    out = rgb_f * (1.0 - blend[..., None]) + fg * blend[..., None]
    return np.clip(out, 0, 255).round().astype(np.uint8)
