from __future__ import annotations

import sys
import types

import torch

from backend.tools.hardware_accelerator import HardwareAccelerator


def _accelerator(*, dml: bool, cuda: bool = False, mps: bool = False):
    accelerator = HardwareAccelerator()
    accelerator._HardwareAccelerator__dml = dml
    accelerator._HardwareAccelerator__cuda = cuda
    accelerator._HardwareAccelerator__mps = mps
    return accelerator


def test_directml_success(monkeypatch) -> None:
    fake = types.SimpleNamespace(default_device=lambda: 0, device=lambda index: "dml:0")
    monkeypatch.setitem(sys.modules, "torch_directml", fake)
    assert _accelerator(dml=True).device == "dml:0"


def test_directml_failure_marks_unavailable_and_falls_back(monkeypatch) -> None:
    fake = types.SimpleNamespace(
        default_device=lambda: 0,
        device=lambda index: (_ for _ in ()).throw(RuntimeError("failure")),
    )
    monkeypatch.setitem(sys.modules, "torch_directml", fake)
    accelerator = _accelerator(dml=True)
    assert accelerator.device == torch.device("cpu")
    assert accelerator.accelerator_name == "CPU"


def test_cuda_fallback_after_directml_failure(monkeypatch) -> None:
    fake = types.SimpleNamespace(
        default_device=lambda: 0,
        device=lambda index: (_ for _ in ()).throw(RuntimeError("failure")),
    )
    monkeypatch.setitem(sys.modules, "torch_directml", fake)
    assert _accelerator(dml=True, cuda=True).device == torch.device("cuda:0")


def test_cuda_has_priority_when_multiple_torch_backends_are_reported() -> None:
    accelerator = _accelerator(dml=True, cuda=True, mps=True)

    assert accelerator.device == torch.device("cuda:0")
    assert accelerator.accelerator_name == "GPU"


def test_tensorrt_is_never_forwarded_to_onnx_sessions(monkeypatch) -> None:
    fake_ort = types.SimpleNamespace(
        get_available_providers=lambda: [
            "TensorrtExecutionProvider",
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    accelerator = _accelerator(dml=False, cuda=True)
    accelerator._HardwareAccelerator__onnx_providers = [
        "TensorrtExecutionProvider",
        "CUDAExecutionProvider",
    ]

    assert accelerator.get_onnx_execution_providers() == [
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]
