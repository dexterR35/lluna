"""VRAM preflight: estimate, pick tile/batch, refuse oversized jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

HEADROOM = 1.5
TILE_CANDIDATES: Tuple[int, ...] = (512, 256, 128, 64)

# Approximate footprints (MB) - calibrated-ish constants, not exact allocator accounting.
_ENHANCE_WEIGHTS_MB = {2: 70.0, 4: 70.0}
_ENHANCE_TILE_ACT_PER_PX = 0.00012  # MB per input tile pixel (incl. pad/scale scratch)
_LAMA_WEIGHTS_MB = 200.0
_LAMA_PER_MPX = 180.0
_SELECT_OBJECT_TINY_MB = 4500.0
_SELECT_OBJECT_COMPLEX_MB = 12000.0
_STTN_BASE_MB = 400.0
_STTN_PER_FRAME_MPX = 90.0
_PROPAINTER_BASE_MB = 800.0
_PROPAINTER_PER_FRAME_MPX = 140.0

# SUPIR and SeedVR2 run in an isolated CUDA subprocess and their VRAM use is
# dominated by fixed model weights, not input resolution - so unlike the
# functions above, these are flat "you need at least this much free" floors
# already inclusive of margin (matching each model's own stated requirement),
# not raw measurements that HEADROOM should be layered on top of.
_SUPIR_MINIMUM_VRAM_MB = 12000.0  # SDXL backbone + VAE + dual CLIP + SUPIR weights
_SUPIR_LLAVA_FP16_EXTRA_MB = 8000.0  # automatic captioning at fp16 (~20GB total)
_SUPIR_LLAVA_8BIT_EXTRA_MB = 4000.0  # automatic captioning, 8-bit quantized
_SEEDVR_MINIMUM_VRAM_MB = {"seedvr2-3b": 24576.0, "seedvr2-7b": 49152.0}


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
    from backend.tools.shared.hardware import HardwareAccelerator

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


def preflight_minimum(tag: str, minimum_mb: float, *, hint: str = "") -> GenericBudget:
    """Flat "is there at least this much VRAM free" check, for jobs whose
    memory use is dominated by fixed model weights rather than input size -
    and for any model (built-in or custom) that only declares a single
    `minimum_vram_mb` figure rather than a calibrated per-input formula.
    A `minimum_mb <= 0` means "unknown/undeclared" and is treated as a no-op
    rather than a hard block, so an undeclared requirement never blocks a run.
    """
    if minimum_mb <= 0 or not _has_cuda_budget():
        return GenericBudget(estimated_mb=0.0, free_mb=0.0)
    free, _ = _free_total_mb()
    if minimum_mb > free:
        raise VramBudgetError(
            f"Not enough GPU memory for {tag} "
            f"(need ~{minimum_mb:.0f} MB free, have {free:.0f} MB)."
            + (f" {hint}" if hint else "")
        )
    return GenericBudget(estimated_mb=minimum_mb, free_mb=free)


def preflight_supir(*, use_llava: bool = False, load_8bit_llava: bool = False) -> GenericBudget:
    est = _SUPIR_MINIMUM_VRAM_MB
    if use_llava:
        est += _SUPIR_LLAVA_8BIT_EXTRA_MB if load_8bit_llava else _SUPIR_LLAVA_FP16_EXTRA_MB
    if use_llava and not load_8bit_llava:
        hint = "Turn on 8-bit LLaVA, turn off automatic captioning, or free up GPU memory."
    elif use_llava:
        hint = "Turn off automatic LLaVA captioning or free up GPU memory."
    else:
        hint = "Free up GPU memory."
    return preflight_minimum("SUPIR", est, hint=hint)


def preflight_seedvr(model_id: str) -> GenericBudget:
    minimum = _SEEDVR_MINIMUM_VRAM_MB.get(model_id)
    if minimum is None:
        return GenericBudget(estimated_mb=0.0, free_mb=0.0)
    hint = (
        "Free up GPU memory."
        if model_id == "seedvr2-3b"
        else "Try the 3B model instead, or free up GPU memory."
    )
    return preflight_minimum("SeedVR2", minimum, hint=hint)


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
