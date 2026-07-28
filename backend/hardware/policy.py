"""Execution recommendations derived from, but not stored in, hardware facts."""

from __future__ import annotations

from dataclasses import dataclass

from backend.hardware.profile import HardwareProfile


@dataclass(frozen=True)
class ExecutionPolicy:
    backend: str
    device: str
    reasons: tuple[str, ...]


def select_execution_policy(
    profile: HardwareProfile, *, acceleration_enabled: bool = True
) -> ExecutionPolicy:
    if not acceleration_enabled:
        return ExecutionPolicy("cpu", "cpu", ("Hardware acceleration is disabled.",))
    caps = profile.capabilities
    # CUDA is the preferred backend whenever it is usable. DirectML and MPS
    # remain GPU fallbacks for machines without CUDA.
    if caps.torch_cuda:
        return ExecutionPolicy("cuda", "cuda:0", ("Torch CUDA is available.",))
    if caps.torch_directml:
        return ExecutionPolicy("directml", "privateuseone", ("DirectML is available.",))
    if caps.torch_mps:
        return ExecutionPolicy("mps", "mps", ("Torch MPS is available.",))
    return ExecutionPolicy("cpu", "cpu", ("No supported accelerator is available.",))
