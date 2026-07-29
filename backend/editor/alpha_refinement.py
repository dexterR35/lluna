"""Deterministic, CPU-safe alpha refinement and protect-mask composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import cv2
import numpy as np

from backend.editor.buffers import BufferKind
from backend.editor.operations import Locality, OperationContract
from backend.media.mask_layers import guided_refine, mask_roi
from backend.tools.cutout_edges import decontaminate_rgb_fringe


ALPHA_REFINE_CONTRACT = OperationContract(
    operation_type="alpha.refine",
    schema_version=1,
    input_kinds=(BufferKind.RGB, BufferKind.MASK),
    output_kinds=(BufferKind.RGBA,),
    locality=Locality.LOCAL,
    padding_px=96,
    tile_overlap_px=32,
    deterministic=True,
    supports_cpu=True,
    supports_proxy=True,
)


@dataclass(frozen=True)
class AlphaRefinementOptions:
    """Source-pixel parameters for the post-segmentation alpha pipeline."""

    enabled: bool = False
    contract_expand_px: float = 0.0
    feather_radius_px: float = 0.0
    edge_smoothing_radius_px: int = 0
    remove_islands_below_px: int = 0
    fill_holes_below_px: int = 0
    decontaminate_rgb: bool = False
    decontaminate_strength: float = 0.65
    protect_mode: str = "binary"

    def __post_init__(self) -> None:
        if not -100.0 <= self.contract_expand_px <= 100.0:
            raise ValueError("contract/expand must be between -100 and 100 pixels")
        if not 0.0 <= self.feather_radius_px <= 100.0:
            raise ValueError("feather radius must be between 0 and 100 pixels")
        if not 0 <= self.edge_smoothing_radius_px <= 100:
            raise ValueError("edge smoothing radius must be between 0 and 100 pixels")
        if not 0 <= self.remove_islands_below_px <= 1_000_000:
            raise ValueError("island cleanup area is out of range")
        if not 0 <= self.fill_holes_below_px <= 1_000_000:
            raise ValueError("hole cleanup area is out of range")
        if not 0.0 <= self.decontaminate_strength <= 1.0:
            raise ValueError("decontamination strength must be between 0 and 1")
        if self.protect_mode not in {"binary", "soft"}:
            raise ValueError("protect mode must be 'binary' or 'soft'")

    @classmethod
    def from_mapping(
        cls, values: Mapping[str, Any] | None
    ) -> AlphaRefinementOptions | None:
        if values is None:
            return None
        allowed = cls.__dataclass_fields__
        unknown = set(values).difference(allowed)
        if unknown:
            raise ValueError(
                f"unknown alpha-refinement setting(s): {', '.join(sorted(unknown))}"
            )
        return cls(**dict(values))


@dataclass(frozen=True)
class AlphaRefinementResult:
    rgba: np.ndarray
    roi: tuple[int, int, int, int] | None
    protected_pixels: int
    changed_alpha_pixels: int


def _as_uint8_2d(mask: np.ndarray, shape: tuple[int, int], *, name: str) -> np.ndarray:
    arr = np.asarray(mask)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional mask")
    if arr.shape != shape:
        raise ValueError(f"{name} dimensions must match the source image")
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return arr


def merge_protect_alpha(
    alpha: np.ndarray,
    protect_mask: np.ndarray | None,
    *,
    mode: str = "binary",
) -> tuple[np.ndarray, int]:
    """Union a keep mask into alpha; no/empty mask is an exact no-op."""
    base = np.asarray(alpha)
    if base.ndim != 2:
        raise ValueError("alpha must be a two-dimensional mask")
    if base.dtype != np.uint8:
        base = np.clip(base, 0, 255).astype(np.uint8)
    if protect_mask is None:
        return base.copy(), 0
    keep = _as_uint8_2d(protect_mask, base.shape, name="protect mask")
    marked = keep > 0
    count = int(np.count_nonzero(marked))
    if count == 0:
        return base.copy(), 0
    if mode == "binary":
        merged = base.copy()
        merged[marked] = 255
        return merged, count
    if mode == "soft":
        return np.maximum(base, keep), count
    raise ValueError("protect mode must be 'binary' or 'soft'")


def _morph_alpha(alpha: np.ndarray, amount: float) -> np.ndarray:
    if abs(amount) < 1e-6:
        return alpha.copy()
    whole = int(abs(amount))
    fraction = abs(amount) - whole
    operation = cv2.dilate if amount > 0 else cv2.erode
    out = alpha.copy()
    if whole:
        size = whole * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        out = operation(out, kernel, iterations=1)
    if fraction > 1e-6:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        next_step = operation(out, kernel, iterations=1)
        out = cv2.addWeighted(out, 1.0 - fraction, next_step, fraction, 0.0)
    return out


def _cleanup_components(
    alpha: np.ndarray,
    *,
    remove_islands_below_px: int,
    fill_holes_below_px: int,
) -> np.ndarray:
    if remove_islands_below_px <= 0 and fill_holes_below_px <= 0:
        return alpha.copy()
    support = (alpha > 0).astype(np.uint8)
    cleaned = support.copy()
    if remove_islands_below_px > 0:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(support, 8)
        for label in range(1, count):
            if int(stats[label, cv2.CC_STAT_AREA]) < remove_islands_below_px:
                cleaned[labels == label] = 0
    out = alpha.copy()
    out[cleaned == 0] = 0
    if fill_holes_below_px <= 0:
        return out

    background = (cleaned == 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(background, 8)
    height, width = background.shape
    for label in range(1, count):
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        component_width = int(stats[label, cv2.CC_STAT_WIDTH])
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        touches_border = (
            left == 0
            or top == 0
            or left + component_width == width
            or top + component_height == height
        )
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not touches_border and area < fill_holes_below_px:
            out[labels == label] = 255
    return out


def _refinement_roi(alpha: np.ndarray, options: AlphaRefinementOptions):
    transition = ((alpha > 0) & (alpha < 255)).astype(np.uint8) * 255
    if not np.any(transition):
        transition = (alpha > 0).astype(np.uint8) * 255
    padding = int(
        max(
            ALPHA_REFINE_CONTRACT.padding_px,
            abs(options.contract_expand_px)
            + options.feather_radius_px * 3.0
            + options.edge_smoothing_radius_px * 2.0,
        )
    )
    return mask_roi(transition, padding=padding, align=8)


def refine_alpha_cutout(
    rgb: np.ndarray,
    model_alpha: np.ndarray,
    options: AlphaRefinementOptions,
    *,
    protect_mask: np.ndarray | None = None,
) -> AlphaRefinementResult:
    """Refine model alpha and RGB without requiring a GPU or model runtime."""
    source = np.asarray(rgb)
    if source.ndim != 3 or source.shape[2] != 3:
        raise ValueError("rgb must have shape HxWx3")
    if source.dtype != np.uint8:
        source = np.clip(source, 0, 255).astype(np.uint8)
    alpha = _as_uint8_2d(
        model_alpha,
        source.shape[:2],
        name="model alpha",
    )
    original_alpha = alpha.copy()
    roi = _refinement_roi(alpha, options)

    if options.enabled:
        alpha = _cleanup_components(
            alpha,
            remove_islands_below_px=options.remove_islands_below_px,
            fill_holes_below_px=options.fill_holes_below_px,
        )
        alpha = _morph_alpha(alpha, options.contract_expand_px)
        if options.edge_smoothing_radius_px > 0:
            alpha = guided_refine(
                alpha,
                source,
                options.edge_smoothing_radius_px,
            )
        if options.feather_radius_px > 0:
            sigma = max(0.1, float(options.feather_radius_px) / 2.0)
            alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=sigma, sigmaY=sigma)

    alpha, protected_pixels = merge_protect_alpha(
        alpha,
        protect_mask,
        mode=options.protect_mode,
    )
    result_rgb = source
    if options.enabled and options.decontaminate_rgb:
        cleaned_rgb = decontaminate_rgb_fringe(source, alpha)
        result_rgb = cv2.addWeighted(
            source,
            1.0 - options.decontaminate_strength,
            cleaned_rgb,
            options.decontaminate_strength,
            0.0,
        )
    rgba = np.dstack((result_rgb, alpha))
    return AlphaRefinementResult(
        rgba=rgba,
        roi=roi,
        protected_pixels=protected_pixels,
        changed_alpha_pixels=int(np.count_nonzero(alpha != original_alpha)),
    )
