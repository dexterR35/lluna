"""Every accelerator is addressable, and mixed machines pick the right one."""

from __future__ import annotations

import pytest

from backend.hardware.policy import select_execution_policy
from backend.hardware.profile import (
    FrameworkCapabilities,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
)
from backend.tools.shared.memory import max_cached_models


def _gpu(index: int, model: str, vram_mb: float, capability: str = "8.9") -> GpuInfo:
    return GpuInfo(
        vendor="NVIDIA",
        model=model,
        total_vram_mb=vram_mb,
        available_vram_mb=vram_mb - 500,
        compute_capability=capability,
        index=index,
        uuid=f"GPU-{index}",
    )


def _profile(*gpus: GpuInfo, cuda: bool = True) -> HardwareProfile:
    return HardwareProfile(
        os_name="Linux",
        os_version="test",
        architecture="x86_64",
        python_architecture="64bit",
        cpu_model="Test CPU",
        memory=MemoryInfo(total_mb=65536.0, available_mb=32768.0),
        gpus=gpus,
        capabilities=FrameworkCapabilities(torch_cuda=cuda),
    )


def test_each_gpu_is_addressable_separately():
    profile = _profile(_gpu(0, "RTX 3060", 12288.0), _gpu(1, "RTX 5090", 32768.0))

    devices = profile.devices()

    assert [device["id"] for device in devices] == ["cpu", "cuda:0", "cuda:1"]
    assert devices[2]["name"] == "RTX 5090"
    assert devices[2]["uuid"] == "GPU-1"


def test_cpu_is_always_a_device():
    devices = _profile(cuda=False).devices()

    assert [device["id"] for device in devices] == ["cpu"]
    assert devices[0]["total_memory_mb"] == 65536.0


def test_mixed_machine_selects_the_larger_card_not_index_zero():
    """A small display GPU enumerated first must not capture the heavy work."""
    profile = _profile(_gpu(0, "RTX 3060", 12288.0), _gpu(1, "RTX 5090", 32768.0))

    policy = select_execution_policy(profile)

    assert policy.device == "cuda:1"
    assert profile.largest_gpu.model == "RTX 5090"


def test_single_gpu_keeps_the_plain_device_string():
    policy = select_execution_policy(_profile(_gpu(0, "RTX 4090", 24564.0)))

    assert policy.device == "cuda:0"


def test_directml_and_mps_are_unaffected_by_gpu_indices():
    profile = HardwareProfile(
        os_name="Darwin",
        os_version="test",
        architecture="arm64",
        python_architecture="64bit",
        capabilities=FrameworkCapabilities(torch_mps=True),
    )

    assert select_execution_policy(profile).device == "mps"


@pytest.mark.parametrize(
    ("total_vram_mb", "expected"),
    [
        (0.0, 1),
        (12288.0, 1),
        (24564.0, 1),
        (49140.0, 2),  # nominal 48 GB reports low; tolerance must still allow 2
        (81559.0, 3),  # nominal 80 GB
    ],
)
def test_cache_budget_follows_installed_vram(total_vram_mb, expected):
    assert max_cached_models(total_vram_mb) == expected


def test_cache_budget_never_drops_below_one():
    assert max_cached_models(0.0) == 1
