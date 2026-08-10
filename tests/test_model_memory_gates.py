"""Model eligibility is judged on installed memory, not momentarily free memory."""

from __future__ import annotations

import pytest

from backend.hardware.profile import GpuInfo, HardwareProfile, MemoryInfo
from backend.models.reference import runtimes
from backend.models.reference.catalog import MODEL_REGISTRY
from backend.models.reference.manifest import (
    HardwareRequirement,
    ModelManifest,
    ModelSource,
    RuntimeRequirement,
)


def _manifest(**hardware) -> ModelManifest:
    return ModelManifest(
        id="example",
        name="Example",
        task="image-upscaling",
        adapter="lluna-native",
        source=ModelSource(type="local"),
        runtime=RuntimeRequirement(profile="lluna-native"),
        hardware=HardwareRequirement(**hardware),
    )


def _profile(*, total_ram_mb, free_ram_mb, total_vram_mb=0.0, free_vram_mb=0.0) -> HardwareProfile:
    gpus = ()
    if total_vram_mb:
        gpus = (
            GpuInfo(
                vendor="NVIDIA",
                model="Test GPU",
                total_vram_mb=total_vram_mb,
                available_vram_mb=free_vram_mb,
            ),
        )
    return HardwareProfile(
        os_name="Linux",
        os_version="test",
        architecture="x86_64",
        python_architecture="64bit",
        memory=MemoryInfo(total_mb=total_ram_mb, available_mb=free_ram_mb),
        gpus=gpus,
        available_disk_mb=1_000_000.0,
    )


@pytest.fixture
def hardware(monkeypatch):
    def apply(profile: HardwareProfile, backend: str = "cuda"):
        monkeypatch.setattr(runtimes, "get_hardware_profile", lambda: profile)
        monkeypatch.setattr(
            runtimes, "select_execution_policy", lambda _profile: type("P", (), {"backend": backend})
        )

    return apply


def test_busy_gpu_warns_instead_of_blocking(hardware):
    """A browser holding VRAM must not make an installed model 'incompatible'."""
    hardware(_profile(total_ram_mb=64000, free_ram_mb=40000, total_vram_mb=24564, free_vram_mb=2000))

    _backend, reasons, warnings = runtimes.compatible_backend(_manifest(backends=("cuda",), minimum_vram_mb=12000))

    assert reasons == ()
    assert any("free right now" in warning for warning in warnings)


def test_card_smaller_than_the_requirement_is_still_rejected(hardware):
    hardware(_profile(total_ram_mb=64000, free_ram_mb=60000, total_vram_mb=8192, free_vram_mb=8000))

    _backend, reasons, _warnings = runtimes.compatible_backend(_manifest(backends=("cuda",), minimum_vram_mb=24576))

    assert any("24576 MB VRAM is required" in reason for reason in reasons)


@pytest.mark.parametrize(
    ("model_id", "total_vram_mb"),
    [("seedvr2-3b", 24564.0), ("seedvr2-7b", 49140.0), ("supir", 12288.0)],
)
def test_nominal_cards_satisfy_their_own_requirement(hardware, model_id, total_vram_mb):
    """A '24 GB' card reports 24564 MB, so a 24576 MB floor must not reject it."""
    model = MODEL_REGISTRY[model_id]
    hardware(
        _profile(
            total_ram_mb=131072,
            free_ram_mb=100000,
            total_vram_mb=total_vram_mb,
            free_vram_mb=total_vram_mb - 500,
        )
    )
    manifest = _manifest(backends=("cuda",), minimum_vram_mb=model.minimum_vram_mb)

    _backend, reasons, _warnings = runtimes.compatible_backend(manifest)

    assert reasons == ()


def test_supir_runs_on_a_32gb_machine(hardware):
    """32 GiB of RAM reports below 32768 MB once firmware takes its share."""
    hardware(_profile(total_ram_mb=31900, free_ram_mb=20000, total_vram_mb=16384, free_vram_mb=16000))
    supir = MODEL_REGISTRY["supir"]
    manifest = _manifest(
        backends=("cuda",),
        minimum_ram_mb=supir.minimum_ram_mb,
        minimum_vram_mb=supir.minimum_vram_mb,
    )

    _backend, reasons, _warnings = runtimes.compatible_backend(manifest)

    assert reasons == ()


def test_unmeasurable_memory_warns_rather_than_blocking(hardware):
    hardware(_profile(total_ram_mb=0.0, free_ram_mb=0.0, total_vram_mb=0.0), backend="cuda")

    _backend, reasons, warnings = runtimes.compatible_backend(
        _manifest(backends=("cuda",), minimum_ram_mb=16384, minimum_vram_mb=8192)
    )

    assert reasons == ()
    assert any("could not be measured" in warning for warning in warnings)


def test_catalog_never_advertises_cpu_for_gpu_only_models():
    """compatible_backend() refuses any VRAM-floored model on cpu, so declaring
    cpu support for one would be a promise the platform cannot keep."""
    offenders = [
        model.id
        for model in MODEL_REGISTRY.values()
        if model.minimum_vram_mb and "cpu" in model.compatible_backends
    ]

    assert offenders == []
