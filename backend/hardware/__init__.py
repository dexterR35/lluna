"""Normalized hardware facts and execution policy."""

from backend.hardware.detector import HardwareDetector, get_hardware_profile
from backend.hardware.policy import ExecutionPolicy, select_execution_policy
from backend.hardware.profile import (
    Confidence,
    FrameworkCapabilities,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
)

__all__ = [
    "Confidence",
    "ExecutionPolicy",
    "FrameworkCapabilities",
    "GpuInfo",
    "HardwareDetector",
    "HardwareProfile",
    "MemoryInfo",
    "get_hardware_profile",
    "select_execution_policy",
]
