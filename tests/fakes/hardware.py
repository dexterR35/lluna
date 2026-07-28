from __future__ import annotations

from backend.hardware.profile import (
    FrameworkCapabilities,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
)


def profile(
    *,
    cuda: bool = False,
    directml: bool = False,
    mps: bool = False,
    onnx: tuple[str, ...] = ("CPUExecutionProvider",),
    vram_mb: float = 0,
    ram_mb: float = 16384,
) -> HardwareProfile:
    gpu = (
        GpuInfo(
            vendor="NVIDIA" if cuda else "Test",
            model="Fake GPU",
            total_vram_mb=vram_mb,
            available_vram_mb=vram_mb * 0.75,
        ),
    ) if (cuda or directml or mps) else ()
    return HardwareProfile(
        os_name="TestOS",
        os_version="1",
        architecture="x86_64",
        python_architecture="64-bit",
        cpu_vendor="Test",
        cpu_model="Deterministic CPU",
        physical_cores=4,
        logical_threads=8,
        memory=MemoryInfo(total_mb=ram_mb, available_mb=ram_mb * 0.75),
        gpus=gpu,
        capabilities=FrameworkCapabilities(
            torch_cuda=cuda,
            torch_directml=directml,
            torch_mps=mps,
            onnx_providers=onnx,
        ),
        ffmpeg_available=True,
        available_disk_mb=100_000,
    )


CPU_ONLY = profile()
CUDA = profile(cuda=True, vram_mb=12288)
DIRECTML = profile(directml=True, vram_mb=8192)
MPS = profile(mps=True, vram_mb=16384)
ONNX_ACCELERATOR = profile(onnx=("CUDAExecutionProvider", "CPUExecutionProvider"))
