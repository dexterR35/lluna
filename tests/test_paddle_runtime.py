from __future__ import annotations

import os
import sys

from backend.ai.runtimes.paddle import (
    disable_paddle_background_services,
    preferred_paddle_device,
)
from backend.hardware import providers


def test_paddle_capability_probe_does_not_import_runtime(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "paddle", raising=False)

    def fake_distribution(name: str):
        if name == "paddlepaddle-gpu":
            raise providers.metadata.PackageNotFoundError(name)
        raise AssertionError(f"unexpected distribution lookup: {name}")

    monkeypatch.setattr(providers.metadata, "distribution", fake_distribution)

    capabilities, warnings = providers.detect_framework_capabilities()

    assert capabilities.paddle_gpu is False
    assert "paddle" not in sys.modules
    assert not any("Paddle capability probe failed" in item for item in warnings)


def test_gpu_paddle_wheel_is_detected_without_runtime_import(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "paddle", raising=False)
    monkeypatch.setattr(
        providers.metadata,
        "distribution",
        lambda name: object() if name == "paddlepaddle-gpu" else None,
    )

    capabilities, _warnings = providers.detect_framework_capabilities()

    assert capabilities.paddle_gpu is True
    assert "paddle" not in sys.modules


def test_paddle_background_dump_threads_are_forced_off(monkeypatch) -> None:
    monkeypatch.setenv("FLAGS_bvar_dump", "true")
    monkeypatch.setenv("FLAGS_mbvar_dump", "true")

    disable_paddle_background_services()

    assert os.environ["FLAGS_bvar_dump"] == "false"
    assert os.environ["FLAGS_mbvar_dump"] == "false"


def test_paddle_prefers_gpu_zero_when_cuda_is_usable() -> None:
    fake = type(
        "FakePaddle",
        (),
        {
            "is_compiled_with_cuda": staticmethod(lambda: True),
            "device": type(
                "Device",
                (),
                {"cuda": type("Cuda", (), {"device_count": staticmethod(lambda: 1)})},
            ),
        },
    )

    assert preferred_paddle_device(fake, acceleration_enabled=True) == "gpu:0"


def test_paddle_falls_back_to_cpu_without_enabled_usable_cuda() -> None:
    no_cuda = type(
        "NoCudaPaddle",
        (),
        {"is_compiled_with_cuda": staticmethod(lambda: False)},
    )
    broken_cuda = type(
        "BrokenCudaPaddle",
        (),
        {
            "is_compiled_with_cuda": staticmethod(lambda: True),
            "device": type(
                "Device",
                (),
                {
                    "cuda": type(
                        "Cuda",
                        (),
                        {
                            "device_count": staticmethod(
                                lambda: (_ for _ in ()).throw(RuntimeError("driver"))
                            )
                        },
                    )
                },
            ),
        },
    )

    assert preferred_paddle_device(no_cuda, acceleration_enabled=True) == "cpu"
    assert preferred_paddle_device(broken_cuda, acceleration_enabled=True) == "cpu"
    assert preferred_paddle_device(broken_cuda, acceleration_enabled=False) == "cpu"
