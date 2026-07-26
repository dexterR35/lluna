"""First-run soft defaults from total VRAM + compute_cap (not GPU series names)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FILE = ROOT / "midgard_runtime.json"


def read_runtime() -> dict:
    try:
        if RUNTIME_FILE.is_file():
            return json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def write_runtime_patch(patch: dict) -> None:
    data = read_runtime()
    data.update(patch)
    try:
        RUNTIME_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def detect_vram_and_cap() -> Tuple[float, Optional[str]]:
    """Return (total_vram_mb, compute_cap or None)."""
    total = 0.0
    cap = None
    try:
        from backend.tools.hardware_accelerator import HardwareAccelerator

        hw = HardwareAccelerator.instance()
        _free, total = hw.get_vram_mb()
    except Exception:
        total = 0.0

    runtime = read_runtime()
    if total <= 0 and runtime.get("total_vram_mb"):
        try:
            total = float(runtime["total_vram_mb"])
        except (TypeError, ValueError):
            pass
    cap = runtime.get("compute_cap")
    if not cap:
        try:
            import subprocess
            import shutil

            smi = shutil.which("nvidia-smi")
            if smi:
                out = subprocess.check_output(
                    [smi, "--query-gpu=memory.total,compute_cap", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=10,
                ).strip()
                if out:
                    parts = [p.strip() for p in out.splitlines()[0].split(",")]
                    if len(parts) >= 1 and total <= 0:
                        total = float(parts[0])
                    if len(parts) >= 2:
                        cap = parts[1]
        except Exception:
            pass
    if total > 0 or cap:
        write_runtime_patch({"total_vram_mb": total or None, "compute_cap": cap})
    return total, cap


def apply_soft_defaults_if_needed() -> bool:
    """
    Apply VRAM-based soft defaults once when config still at factory values.
    Inpaint mode stays STTN Smart Inpainting (sttn-auto) - only batch sizes nudge.
    Returns True if defaults were applied.
    """
    from backend.config import config
    from backend.tools.constant import InpaintMode

    if bool(config.softDefaultsApplied.value):
        return False

    total_mb, compute_cap = detect_vram_and_cap()
    # Only nudge if user has not customized key items much - check factory-ish values.
    sttn_default = 50
    prop_default = 70
    mode_default = InpaintMode.STTN_AUTO

    customized = (
        config.sttnMaxLoadNum.value != sttn_default
        or config.propainterMaxLoadNum.value != prop_default
        or config.inpaintMode.value != mode_default
    )
    if customized:
        config.set(config.softDefaultsApplied, True)
        return False

    gb = total_mb / 1024.0 if total_mb else 0.0
    try:
        cap_f = float(compute_cap) if compute_cap else 0.0
    except ValueError:
        cap_f = 0.0

    # Always keep STTN Smart Inpainting as the default model on first run
    config.set(config.inpaintMode, InpaintMode.STTN_AUTO)

    if gb <= 0 or gb < 4:
        config.set(config.sttnMaxLoadNum, 20)
        config.set(config.propainterMaxLoadNum, 20)
    elif gb < 8:
        config.set(config.sttnMaxLoadNum, 30)
        config.set(config.propainterMaxLoadNum, 30)
    elif gb < 12:
        config.set(config.sttnMaxLoadNum, 40)
        config.set(config.propainterMaxLoadNum, 50)
    # else: keep factory load nums

    # Very old GPUs: smaller STTN batches only (do not switch away from STTN Smart)
    if 0 < cap_f < 6.0:
        config.set(config.sttnMaxLoadNum, min(int(config.sttnMaxLoadNum.value), 20))
        config.set(config.propainterMaxLoadNum, min(int(config.propainterMaxLoadNum.value), 20))

    config.set(config.softDefaultsApplied, True)
    write_runtime_patch({"soft_defaults_applied": True, "total_vram_mb": total_mb, "compute_cap": compute_cap})
    return True
