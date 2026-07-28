"""System memory detection."""

from __future__ import annotations

from backend.hardware.profile import MemoryInfo


def detect_memory() -> MemoryInfo:
    try:
        import psutil

        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        scale = 1024 * 1024
        return MemoryInfo(
            total_mb=vm.total / scale,
            available_mb=vm.available / scale,
            swap_total_mb=swap.total / scale,
            swap_available_mb=swap.free / scale,
        )
    except (ImportError, OSError):
        return MemoryInfo()
