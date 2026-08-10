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
    # Ordinal within this machine, and the driver's stable identifier for it.
    # `index` is what makes a GPU addressable as cuda:<index>; `uuid` survives
    # reordering (CUDA_VISIBLE_DEVICES, a card moving slots) in a way index does not.
    index: int = 0
    uuid: str = ""

    @property
    def device_id(self) -> str:
        return f"cuda:{self.index}" if self.vendor.upper() == "NVIDIA" else "gpu"

    def compute_capability_value(self) -> float:
        try:
            return float(self.compute_capability)
        except (TypeError, ValueError):
            return 0.0


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

    @property
    def largest_gpu(self) -> GpuInfo | None:
        """The GPU with the most VRAM, which is rarely index 0 on mixed machines."""
        return max(self.gpus, key=lambda gpu: gpu.total_vram_mb, default=None)

    def devices(self) -> tuple[dict[str, Any], ...]:
        """Every execution target on this machine, addressable by id.

        The CPU is always present. Each GPU appears under its own id rather than
        being collapsed into one "the GPU" entry, so a machine with two cards can
        be told apart from a machine with one.
        """
        entries: list[dict[str, Any]] = [
            {
                "id": "cpu",
                "backend": "cpu",
                "name": self.cpu_model or "CPU",
                "total_memory_mb": self.memory.total_mb,
                "available_memory_mb": self.memory.available_mb,
            }
        ]
        caps = self.capabilities
        for gpu in self.gpus:
            if gpu.vendor.upper() == "NVIDIA" and caps.torch_cuda:
                backend = "cuda"
            elif caps.torch_directml:
                backend = "directml"
            elif caps.torch_mps:
                backend = "mps"
            else:
                backend = "unavailable"
            entries.append(
                {
                    "id": gpu.device_id if backend == "cuda" else backend,
                    "backend": backend,
                    "name": gpu.model or f"{gpu.vendor} GPU".strip(),
                    "index": gpu.index,
                    "uuid": gpu.uuid,
                    "total_memory_mb": gpu.total_vram_mb,
                    "available_memory_mb": gpu.available_vram_mb,
                    "compute_capability": gpu.compute_capability,
                }
            )
        return tuple(entries)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
