"""Immutable, serializable hardware facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Confidence(str, Enum):
    VERIFIED = "verified"
    REPORTED = "reported"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MemoryInfo:
    total_mb: float = 0.0
    available_mb: float = 0.0
    swap_total_mb: float = 0.0
    swap_available_mb: float = 0.0


@dataclass(frozen=True)
class GpuInfo:
    vendor: str = ""
    model: str = ""
    total_vram_mb: float = 0.0
    available_vram_mb: float = 0.0
    driver_version: str = ""
    cuda_driver_version: str = ""
    cuda_runtime_version: str = ""
    compute_capability: str = ""
    confidence: Confidence = Confidence.UNKNOWN


@dataclass(frozen=True)
class FrameworkCapabilities:
    torch_cuda: bool = False
    torch_directml: bool = False
    torch_mps: bool = False
    paddle_gpu: bool = False
    cpu: bool = True


@dataclass(frozen=True)
class HardwareProfile:
    os_name: str
    os_version: str
    architecture: str
    python_architecture: str
    cpu_vendor: str = ""
    cpu_model: str = ""
    physical_cores: int = 0
    logical_threads: int = 0
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    gpus: tuple[GpuInfo, ...] = ()
    capabilities: FrameworkCapabilities = field(default_factory=FrameworkCapabilities)
    ffmpeg_available: bool = False
    available_disk_mb: float = 0.0
    warnings: tuple[str, ...] = ()

    @property
    def primary_gpu(self) -> GpuInfo | None:
        return self.gpus[0] if self.gpus else None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
