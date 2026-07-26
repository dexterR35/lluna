"""VRAM preflight: estimate, pick tile/batch, refuse oversized jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

HEADROOM = 1.5
TILE_CANDIDATES: Tuple[int, ...] = (512, 256, 128, 64)

# Approximate footprints (MB) - calibrated-ish constants, not exact allocator accounting.
_ENHANCE_WEIGHTS_MB = {2: 70.0, 4: 70.0}
_ENHANCE_TILE_ACT_PER_PX = 0.00012  # MB per input tile pixel (incl. pad/scale scratch)
_REMBG_SESSION_MB = 900.0
_LAMA_WEIGHTS_MB = 200.0
_LAMA_PER_MPX = 180.0
_SELECT_OBJECT_TINY_MB = 4500.0
_SELECT_OBJECT_COMPLEX_MB = 12000.0
_STTN_BASE_MB = 400.0
_STTN_PER_FRAME_MPX = 90.0
_PROPAINTER_BASE_MB = 800.0
_PROPAINTER_PER_FRAME_MPX = 140.0


class VramBudgetError(RuntimeError):
    """Job cannot fit in available VRAM (or size caps)."""


@dataclass(frozen=True)
class EnhanceBudget:
    tile: int
    outscale_ok: bool
    estimated_mb: float
    free_mb: float


@dataclass(frozen=True)
class GenericBudget:
    estimated_mb: float
    free_mb: float
    param: Optional[int] = None  # e.g. maxLoadNum or batch


def _free_total_mb() -> Tuple[float, float]:
    from backend.tools.hardware_accelerator import HardwareAccelerator

    hw = HardwareAccelerator.instance()
    return hw.get_vram_mb()


def _has_cuda_budget() -> bool:
    free, total = _free_total_mb()
    return total > 0 and free >= 0


def _with_headroom(mb: float) -> float:
    return float(mb) * HEADROOM


def estimate_enhance_mb(h: int, w: int, scale: int, tile: int) -> float:
    weights = _ENHANCE_WEIGHTS_MB.get(int(scale), 70.0)
    t = max(64, int(tile))
    # One padded tile forward + output buffer proportional to full frame at scale.
    tile_area = float((t + 20) * (t + 20))
    frame_out = float(h * w) * float(scale) * float(scale) * 4e-6  # rough output scratch
    act = tile_area * _ENHANCE_TILE_ACT_PER_PX * float(scale) * float(scale)
    return weights + act + frame_out


def pick_enhance_tile(
    h: int,
    w: int,
    scale: int,
    max_long_edge: int,
    candidates: Sequence[int] = TILE_CANDIDATES,
) -> EnhanceBudget:
    long_edge = max(h, w)
    if long_edge > max_long_edge * 4:
        # Extreme inputs even before upscale.
        raise VramBudgetError(
            f"Image too large ({w}x{h}); max long edge is {max_long_edge}."
        )

    if not _has_cuda_budget():
        # CPU / MPS / DML: long-edge only; use default tile.
        tile = int(candidates[1] if len(candidates) > 1 else 256)
        return EnhanceBudget(tile=tile, outscale_ok=True, estimated_mb=0.0, free_mb=0.0)

    free, _total = _free_total_mb()
    last_est = 0.0
    for tile in candidates:
        est = estimate_enhance_mb(h, w, scale, tile)
        last_est = est
        if _with_headroom(est) <= free:
            return EnhanceBudget(
                tile=int(tile),
                outscale_ok=True,
                estimated_mb=est,
                free_mb=free,
            )

    raise VramBudgetError(
        f"Not enough GPU memory for enhance "
        f"(need ~{_with_headroom(last_est):.0f} MB free, have {free:.0f} MB). "
        f"Try a smaller image, x2 instead of x4, or close other GPU apps."
    )


def next_smaller_tile(tile: int, candidates: Sequence[int] = TILE_CANDIDATES) -> Optional[int]:
    ordered = sorted((int(c) for c in candidates), reverse=True)
    for i, t in enumerate(ordered):
        if t == int(tile) and i + 1 < len(ordered):
            return ordered[i + 1]
    smaller = [t for t in ordered if t < int(tile)]
    return smaller[0] if smaller else None


def preflight_rembg(h: int, w: int, max_long_edge: int = 0) -> GenericBudget:
    long_edge = max(h, w)
    if max_long_edge and max_long_edge > 0 and long_edge > max_long_edge:
        # Caller may resize; still allow when uncapped (0).
        pass
    if not _has_cuda_budget():
        return GenericBudget(estimated_mb=0.0, free_mb=0.0)
    free, _ = _free_total_mb()
    est = _REMBG_SESSION_MB + (h * w * 8e-6)
    if _with_headroom(est) > free and free < 500:
        raise VramBudgetError(
            f"Not enough GPU memory for background removal "
            f"(need ~{_with_headroom(est):.0f} MB free, have {free:.0f} MB)."
        )
    return GenericBudget(estimated_mb=est, free_mb=free)


def preflight_lama(h: int, w: int) -> GenericBudget:
    if not _has_cuda_budget():
        return GenericBudget(estimated_mb=0.0, free_mb=0.0)
    free, _ = _free_total_mb()
    mpx = (h * w) / 1_000_000.0
    est = _LAMA_WEIGHTS_MB + _LAMA_PER_MPX * mpx
    if _with_headroom(est) > free:
        raise VramBudgetError(
            f"Not enough GPU memory for LAMA retouch "
            f"(need ~{_with_headroom(est):.0f} MB free, have {free:.0f} MB)."
        )
    return GenericBudget(estimated_mb=est, free_mb=free)


def preflight_select_subject(h: int, w: int, *, complex_pair: bool = False) -> GenericBudget:
    if not _has_cuda_budget():
        return GenericBudget(estimated_mb=0.0, free_mb=0.0)
    free, _ = _free_total_mb()
    mpx = (h * w) / 1_000_000.0
    base = _SELECT_OBJECT_COMPLEX_MB if complex_pair else _SELECT_OBJECT_TINY_MB
    est = base + 80.0 * mpx
    if _with_headroom(est) > free:
        raise VramBudgetError(
            f"Not enough GPU memory for Select Object "
            f"(need ~{_with_headroom(est):.0f} MB free, have {free:.0f} MB). "
            f"Turn off More complex in Settings or use a smaller image."
        )
    return GenericBudget(estimated_mb=est, free_mb=free)


def pick_video_load_num(
    h: int,
    w: int,
    requested: int,
    *,
    propainter: bool = False,
    min_load: int = 4,
) -> GenericBudget:
    """Shrink max concurrent frames to fit free VRAM; refuse if min cannot fit."""
    if not _has_cuda_budget():
        return GenericBudget(estimated_mb=0.0, free_mb=0.0, param=int(requested))

    free, _ = _free_total_mb()
    mpx = (h * w) / 1_000_000.0
    base = _PROPAINTER_BASE_MB if propainter else _STTN_BASE_MB
    per = _PROPAINTER_PER_FRAME_MPX if propainter else _STTN_PER_FRAME_MPX

    n = max(min_load, int(requested))
    while n >= min_load:
        est = base + per * mpx * n
        if _with_headroom(est) <= free:
            return GenericBudget(estimated_mb=est, free_mb=free, param=n)
        n -= 2 if n > min_load + 2 else 1

    est = base + per * mpx * min_load
    raise VramBudgetError(
        f"Not enough GPU memory for video inpaint "
        f"(need ~{_with_headroom(est):.0f} MB free, have {free:.0f} MB). "
        f"Try a lighter mode (LAMA/OpenCV) or lower Max Concurrent Frames."
    )


def log_budget(tag: str, estimated_mb: float, free_mb: float, **extra) -> str:
    bits = [f"{tag}: est={estimated_mb:.0f}MB free={free_mb:.0f}MB headroom={HEADROOM}"]
    for k, v in extra.items():
        bits.append(f"{k}={v}")
    return " ".join(bits)
