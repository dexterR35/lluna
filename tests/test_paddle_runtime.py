from __future__ import annotations

import os
import sys

from backend.hardware import providers
from backend.tools.paddle_runtime import disable_paddle_background_services


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


def test_onnx_probe_rejects_unsupported_and_unloadable_providers(monkeypatch) -> None:
    fake_ort = type(
        "FakeOrt",
        (),
        {
            "__file__": None,
            "get_available_providers": staticmethod(
                lambda: [
                    "TensorrtExecutionProvider",
                    "CUDAExecutionProvider",
                    "CPUExecutionProvider",
                ]
            ),
        },
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    monkeypatch.setattr(providers, "_cuda_provider_library_ready", lambda ort: False)

    capabilities, warnings = providers.detect_framework_capabilities()

    assert capabilities.onnx_providers == ("CPUExecutionProvider",)
    assert any("TensorrtExecutionProvider" in item for item in warnings)
    assert any("CUDA/cuDNN" in item for item in warnings)


def test_paddle_background_dump_threads_are_forced_off(monkeypatch) -> None:
    monkeypatch.setenv("FLAGS_bvar_dump", "true")
    monkeypatch.setenv("FLAGS_mbvar_dump", "true")

    disable_paddle_background_services()

    assert os.environ["FLAGS_bvar_dump"] == "false"
    assert os.environ["FLAGS_mbvar_dump"] == "false"
