"""Cached, normalized hardware detection."""

from __future__ import annotations

import platform
import shutil
import struct
import threading
from pathlib import Path

from backend.core.paths import PATHS, AppPaths
from backend.hardware.cpu import detect_cpu
from backend.hardware.gpu import detect_gpus
from backend.hardware.memory import detect_memory
from backend.hardware.profile import HardwareProfile
from backend.hardware.providers import detect_framework_capabilities


class HardwareDetector:
    def __init__(self, paths: AppPaths = PATHS) -> None:
        self._paths = paths
        self._lock = threading.Lock()
        self._cached: HardwareProfile | None = None

    def detect(self, *, refresh: bool = False) -> HardwareProfile:
        with self._lock:
            if self._cached is not None and not refresh:
                return self._cached
            self._cached = self._detect_uncached()
            return self._cached

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None

    def _detect_uncached(self) -> HardwareProfile:
        warnings: list[str] = []
        try:
            vendor, model, physical, logical = detect_cpu()
        except Exception as exc:
            vendor, model, physical, logical = "", "", 0, 0
            warnings.append(f"CPU probe failed: {type(exc).__name__}")
        try:
            memory = detect_memory()
        except Exception as exc:
            from backend.hardware.profile import MemoryInfo

            memory = MemoryInfo()
            warnings.append(f"Memory probe failed: {type(exc).__name__}")
        try:
            capabilities, provider_warnings = detect_framework_capabilities()
            warnings.extend(provider_warnings)
        except Exception as exc:
            from backend.hardware.profile import FrameworkCapabilities

            capabilities = FrameworkCapabilities()
            warnings.append(f"Provider probe failed: {type(exc).__name__}")
        try:
            gpus = detect_gpus()
        except Exception as exc:
            gpus = ()
            warnings.append(f"GPU probe failed: {type(exc).__name__}")
        try:
            disk_mb = shutil.disk_usage(Path(self._paths.project_root)).free / (
                1024 * 1024
            )
        except OSError as exc:
            disk_mb = 0.0
            warnings.append(f"Disk probe failed: {type(exc).__name__}")
        ffmpeg = shutil.which("ffmpeg") is not None or any(
            path.is_file()
            for path in (
                self._paths.project_root / "backend/ffmpeg/linux_x64/ffmpeg",
                self._paths.project_root / "backend/ffmpeg/macos/ffmpeg",
                self._paths.project_root / "backend/ffmpeg/win_x64/ffmpeg_1.exe",
            )
        )
        return HardwareProfile(
            os_name=platform.system(),
            os_version=platform.version(),
            architecture=platform.machine(),
            python_architecture=f"{struct.calcsize('P') * 8}-bit",
            cpu_vendor=vendor,
            cpu_model=model,
            physical_cores=physical,
            logical_threads=logical,
            memory=memory,
            gpus=gpus,
            capabilities=capabilities,
            ffmpeg_available=ffmpeg,
            available_disk_mb=disk_mb,
            warnings=tuple(warnings),
        )


DEFAULT_DETECTOR = HardwareDetector()


def get_hardware_profile(*, refresh: bool = False) -> HardwareProfile:
    return DEFAULT_DETECTOR.detect(refresh=refresh)
