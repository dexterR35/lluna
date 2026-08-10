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
        # On a mixed machine the biggest card, not index 0, is the one that
        # decides which models fit; addressing it explicitly keeps heavy work off
        # a small display GPU that happens to be enumerated first.
        gpu = profile.largest_gpu
        if gpu is not None and len(profile.gpus) > 1:
            return ExecutionPolicy(
                "cuda",
                gpu.device_id,
                (f"Torch CUDA is available; selected {gpu.model or gpu.device_id}.",),
            )
        return ExecutionPolicy("cuda", "cuda:0", ("Torch CUDA is available.",))
    if caps.torch_directml:
        return ExecutionPolicy("directml", "privateuseone", ("DirectML is available.",))
    if caps.torch_mps:
        return ExecutionPolicy("mps", "mps", ("Torch MPS is available.",))
    return ExecutionPolicy("cpu", "cpu", ("No supported accelerator is available.",))
