"""CPU detection with standard-library fallbacks."""

from __future__ import annotations

import os
import platform


def detect_cpu() -> tuple[str, str, int, int]:
    model = platform.processor() or platform.machine()
    vendor = ""
    lower = model.lower()
    if "intel" in lower:
        vendor = "Intel"
    elif "amd" in lower:
        vendor = "AMD"
    elif "apple" in lower:
        vendor = "Apple"
    logical = os.cpu_count() or 0
    physical = 0
    try:
        import psutil

        physical = psutil.cpu_count(logical=False) or 0
        logical = psutil.cpu_count(logical=True) or logical
    except (ImportError, OSError):
        pass
    return vendor, model, physical, logical
