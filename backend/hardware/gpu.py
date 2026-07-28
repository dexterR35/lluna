"""GPU facts from framework APIs without making execution decisions."""

from __future__ import annotations

import csv
import shutil
import subprocess
from dataclasses import replace

from backend.hardware.profile import Confidence, GpuInfo


def detect_nvidia_smi_gpus() -> tuple[GpuInfo, ...]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return ()
    try:
        output = subprocess.check_output(
            [
                executable,
                "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=8,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ()
    detected: list[GpuInfo] = []
    for row in csv.reader(output.splitlines()):
        if len(row) < 5:
            continue
        try:
            total = float(row[1].strip())
            available = float(row[2].strip())
        except ValueError:
            total = available = 0.0
        detected.append(
            GpuInfo(
                vendor="NVIDIA",
                model=row[0].strip(),
                total_vram_mb=total,
                available_vram_mb=available,
                driver_version=row[3].strip(),
                cuda_driver_version="",
                compute_capability=row[4].strip(),
                confidence=Confidence.REPORTED,
            )
        )
    return tuple(detected)


def detect_torch_cuda_gpus() -> tuple[GpuInfo, ...]:
    try:
        import torch

        if not torch.cuda.is_available():
            return ()
        gpus: list[GpuInfo] = []
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            total = float(props.total_memory) / (1024 * 1024)
            free = 0.0
            try:
                free_b, _ = torch.cuda.mem_get_info(index)
                free = float(free_b) / (1024 * 1024)
            except (RuntimeError, TypeError):
                pass
            major = getattr(props, "major", None)
            minor = getattr(props, "minor", None)
            capability = (
                f"{major}.{minor}" if major is not None and minor is not None else ""
            )
            gpus.append(
                GpuInfo(
                    vendor="NVIDIA",
                    model=props.name,
                    total_vram_mb=total,
                    available_vram_mb=free,
                    cuda_runtime_version=str(getattr(torch.version, "cuda", "") or ""),
                    compute_capability=capability,
                    confidence=Confidence.VERIFIED,
                )
            )
        return tuple(gpus)
    except (ImportError, OSError, RuntimeError):
        return ()


def detect_gpus() -> tuple[GpuInfo, ...]:
    """Merge dynamic framework facts with driver-reported NVIDIA metadata."""
    torch_gpus = detect_torch_cuda_gpus()
    reported_gpus = detect_nvidia_smi_gpus()
    if not torch_gpus:
        return reported_gpus
    merged: list[GpuInfo] = []
    for index, torch_gpu in enumerate(torch_gpus):
        if index >= len(reported_gpus):
            merged.append(torch_gpu)
            continue
        reported = reported_gpus[index]
        merged.append(
            replace(
                torch_gpu,
                model=torch_gpu.model or reported.model,
                total_vram_mb=torch_gpu.total_vram_mb
                or reported.total_vram_mb,
                available_vram_mb=torch_gpu.available_vram_mb
                or reported.available_vram_mb,
                driver_version=reported.driver_version,
                cuda_driver_version=reported.cuda_driver_version,
                compute_capability=torch_gpu.compute_capability
                or reported.compute_capability,
                confidence=Confidence.VERIFIED,
            )
        )
    return tuple(merged)
