from __future__ import annotations

from backend.hardware import gpu
from backend.hardware.profile import Confidence, GpuInfo


def test_nvidia_smi_detection_normalizes_driver_and_memory(monkeypatch) -> None:
    monkeypatch.setattr(gpu.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        gpu.subprocess,
        "check_output",
        lambda *args, **kwargs: "RTX 4070, 12282, 8192, 555.42, 8.9\n",
    )
    detected = gpu.detect_nvidia_smi_gpus()
    assert detected == (
        GpuInfo(
            vendor="NVIDIA",
            model="RTX 4070",
            total_vram_mb=12282,
            available_vram_mb=8192,
            driver_version="555.42",
            compute_capability="8.9",
            confidence=Confidence.REPORTED,
        ),
    )


def test_gpu_detection_falls_back_to_driver_when_torch_cpu(monkeypatch) -> None:
    reported = GpuInfo(vendor="NVIDIA", model="GPU", confidence=Confidence.REPORTED)
    monkeypatch.setattr(gpu, "detect_torch_cuda_gpus", lambda: ())
    monkeypatch.setattr(gpu, "detect_nvidia_smi_gpus", lambda: (reported,))
    assert gpu.detect_gpus() == (reported,)
