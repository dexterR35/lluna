"""First-run soft defaults from total VRAM + compute_cap (not GPU series names)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS

RUNTIME_FILE = PATHS.runtime_file
logger = logging.getLogger(__name__)


def read_runtime() -> dict:
    try:
        if RUNTIME_FILE.is_file():
            return json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning("Could not read runtime state: %s", type(exc).__name__)
    return {}


def write_runtime_patch(patch: dict) -> None:
    data = read_runtime()
    data.update(patch)
    try:
        atomic_write_json(RUNTIME_FILE, data)
    except OSError as exc:
        logger.warning("Could not save runtime state: %s", type(exc).__name__)


def detect_vram_and_cap() -> Tuple[float, Optional[str]]:
    """Return (total_vram_mb, compute_cap or None)."""
    total = 0.0
    cap = None
    try:
        from backend.hardware.detector import get_hardware_profile

        profile = get_hardware_profile()
        gpu = profile.primary_gpu
        if gpu is not None:
            total = gpu.total_vram_mb
            cap = gpu.compute_capability or None
    except (ImportError, OSError, RuntimeError) as exc:
        logger.warning("Hardware profile unavailable: %s", type(exc).__name__)

    runtime = read_runtime()
    if total <= 0 and runtime.get("total_vram_mb"):
        try:
            total = float(runtime["total_vram_mb"])
        except (TypeError, ValueError):
            pass
    cap = cap or runtime.get("compute_cap")
    if not cap:
        cap = None
    if total > 0 or cap:
        write_runtime_patch({"total_vram_mb": total or None, "compute_cap": cap})
    return total, cap


def apply_soft_defaults_if_needed() -> bool:
    """Apply VRAM-based defaults once without mutating saved configuration."""
    from backend.configuration.service import get_settings, update_settings

    settings = get_settings()
    if settings.runtime.soft_defaults_applied:
        return False

    total_mb, compute_cap = detect_vram_and_cap()
    subtitle = settings.subtitle
    customized = (
        subtitle.sttn_max_load_num != 50
        or subtitle.propainter_max_load_num != 70
        or subtitle.inpaint_mode != "sttn-auto"
    )
    if customized:
        update_settings({"runtime": {"soft_defaults_applied": True}})
        return False

    gb = total_mb / 1024.0 if total_mb else 0.0
    try:
        cap_f = float(compute_cap) if compute_cap else 0.0
    except ValueError:
        cap_f = 0.0

    sttn_max, propainter_max = 50, 70
    if gb <= 0 or gb < 4:
        sttn_max, propainter_max = 20, 20
    elif gb < 8:
        sttn_max, propainter_max = 30, 30
    elif gb < 12:
        sttn_max, propainter_max = 40, 50
    if 0 < cap_f < 6.0:
        sttn_max = min(sttn_max, 20)
        propainter_max = min(propainter_max, 20)

    update_settings({
        "runtime": {"soft_defaults_applied": True},
        "subtitle": {
            "inpaint_mode": "sttn-auto",
            "sttn_max_load_num": sttn_max,
            "propainter_max_load_num": propainter_max,
        },
    })
    write_runtime_patch({
        "soft_defaults_applied": True,
        "total_vram_mb": total_mb,
        "compute_cap": compute_cap,
    })
    return True
