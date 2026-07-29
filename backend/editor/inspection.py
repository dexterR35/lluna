"""Color-stable CPU views for before/after and alpha inspection."""

from __future__ import annotations

from enum import Enum

import numpy as np
from PIL import Image


class InspectionMode(str, Enum):
    ORIGINAL = "original"
    RESULT = "result"
    WIPE = "wipe"
    ALPHA = "alpha"
    CHECKERBOARD = "checkerboard"
    BLACK = "black"
    WHITE = "white"
    RED_OVERLAY = "red_overlay"
    DIFFERENCE = "difference"


def _rgba(image: Image.Image) -> Image.Image:
    value = image.convert("RGBA")
    value.load()
    return value


def align_for_comparison(
    original: Image.Image,
    result: Image.Image,
) -> tuple[Image.Image, Image.Image, bool]:
    """Align to result pixels; report when the original required resampling."""
    before = _rgba(original)
    after = _rgba(result)
    resampled = before.size != after.size
    if resampled:
        before = before.resize(after.size, Image.Resampling.LANCZOS)
    return before, after, resampled


def checkerboard(
    size: tuple[int, int],
    *,
    tile: int = 12,
    light: tuple[int, int, int] = (190, 190, 190),
    dark: tuple[int, int, int] = (120, 120, 120),
) -> Image.Image:
    width, height = size
    if width < 1 or height < 1:
        raise ValueError("checkerboard dimensions must be positive")
    tile = max(1, int(tile))
    y = np.arange(height, dtype=np.int32)[:, None]
    x = np.arange(width, dtype=np.int32)[None, :]
    parity = ((x // tile + y // tile) & 1).astype(bool)
    array = np.empty((height, width, 4), dtype=np.uint8)
    array[:, :, :3] = np.where(
        parity[:, :, None],
        np.asarray(dark, dtype=np.uint8),
        np.asarray(light, dtype=np.uint8),
    )
    array[:, :, 3] = 255
    return Image.fromarray(array, mode="RGBA")


def composite_on(
    image: Image.Image,
    background: tuple[int, int, int] | Image.Image,
) -> Image.Image:
    foreground = _rgba(image)
    if isinstance(background, Image.Image):
        base = _rgba(background)
        if base.size != foreground.size:
            raise ValueError("background dimensions must match the image")
    else:
        base = Image.new("RGBA", foreground.size, (*background, 255))
    return Image.alpha_composite(base, foreground)


def render_inspection(
    original: Image.Image,
    result: Image.Image,
    mode: InspectionMode | str,
    *,
    checker_tile: int = 12,
) -> Image.Image:
    selected = mode if isinstance(mode, InspectionMode) else InspectionMode(mode)
    before, after, _ = align_for_comparison(original, result)
    if selected is InspectionMode.ORIGINAL:
        return before
    if selected is InspectionMode.RESULT:
        return after
    if selected is InspectionMode.CHECKERBOARD:
        return composite_on(after, checkerboard(after.size, tile=checker_tile))
    if selected is InspectionMode.BLACK:
        return composite_on(after, (0, 0, 0))
    if selected is InspectionMode.WHITE:
        return composite_on(after, (255, 255, 255))

    after_array = np.asarray(after, dtype=np.uint8)
    alpha = after_array[:, :, 3]
    if selected is InspectionMode.ALPHA:
        output = np.empty_like(after_array)
        output[:, :, :3] = alpha[:, :, None]
        output[:, :, 3] = 255
        return Image.fromarray(output, mode="RGBA")
    if selected is InspectionMode.RED_OVERLAY:
        base = np.asarray(before, dtype=np.uint8).copy()
        removed = (255 - alpha).astype(np.uint16)
        overlay_alpha = (removed * 140 // 255).astype(np.uint16)
        base_rgb = base[:, :, :3].astype(np.uint16)
        red = np.array([255, 40, 40], dtype=np.uint16)
        base[:, :, :3] = (
            (
                base_rgb * (255 - overlay_alpha[:, :, None])
                + red * overlay_alpha[:, :, None]
            )
            // 255
        ).astype(np.uint8)
        base[:, :, 3] = 255
        return Image.fromarray(base, mode="RGBA")
    if selected is InspectionMode.DIFFERENCE:
        rendered = np.asarray(
            composite_on(after, checkerboard(after.size, tile=checker_tile)),
            dtype=np.int16,
        )
        original_array = np.asarray(before, dtype=np.int16)
        difference = np.abs(original_array[:, :, :3] - rendered[:, :, :3])
        boosted = np.clip(difference * 3, 0, 255).astype(np.uint8)
        alpha_difference = 255 - alpha
        boosted[:, :, 0] = np.maximum(boosted[:, :, 0], alpha_difference)
        output = np.dstack((boosted, np.full(alpha.shape, 255, dtype=np.uint8)))
        return Image.fromarray(output, mode="RGBA")
    raise ValueError(f"{selected.value} requires wipe_comparison")


def wipe_comparison(
    original: Image.Image,
    result: Image.Image,
    position: float,
    *,
    checker_tile: int = 12,
) -> Image.Image:
    """Original on the left, checkerboard-composited result on the right."""
    if not 0.0 <= float(position) <= 1.0:
        raise ValueError("wipe position must be between 0 and 1")
    before, after, _ = align_for_comparison(original, result)
    left = np.asarray(before, dtype=np.uint8)
    right = np.asarray(
        composite_on(after, checkerboard(after.size, tile=checker_tile)),
        dtype=np.uint8,
    )
    output = right.copy()
    split = int(round(after.width * float(position)))
    output[:, :split] = left[:, :split]
    if 0 < split < after.width:
        start = max(0, split - 1)
        end = min(after.width, split + 1)
        output[:, start:end, :3] = 255
        output[:, start:end, 3] = 255
    return Image.fromarray(output, mode="RGBA")
