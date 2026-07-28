"""Optional framework capability probes; every probe is failure-isolated."""

from __future__ import annotations

import importlib.util
from importlib import metadata

from backend.hardware.profile import FrameworkCapabilities


def _paddle_gpu_build_installed() -> bool:
    """Detect Paddle's GPU build without importing its native runtime.

    Importing Paddle starts BRPC process-metric machinery.  Hardware detection
    runs in both the GUI and the idle inference worker, so a runtime import here
    would keep Paddle background services alive before OCR is ever requested.
    """
    try:
        metadata.distribution("paddlepaddle-gpu")
    except metadata.PackageNotFoundError:
        return False
    return True


def detect_framework_capabilities() -> tuple[FrameworkCapabilities, tuple[str, ...]]:
    warnings: list[str] = []
    torch_cuda = torch_mps = False
    try:
        import torch

        torch_cuda = bool(torch.cuda.is_available())
        mps = getattr(torch.backends, "mps", None)
        torch_mps = bool(mps and mps.is_built() and mps.is_available())
    except (ImportError, OSError, RuntimeError) as exc:
        warnings.append(f"Torch capability probe failed: {type(exc).__name__}")

    directml = importlib.util.find_spec("torch_directml") is not None
    providers: tuple[str, ...] = ()
    try:
        import onnxruntime as ort

        providers = tuple(ort.get_available_providers())
    except (ImportError, OSError, RuntimeError) as exc:
        warnings.append(f"ONNX Runtime probe failed: {type(exc).__name__}")

    # Do not import Paddle as a startup capability probe.  The GPU wheel name is
    # enough for diagnostics; actual OCR initialization remains lazy and
    # failure-isolated inside the inference worker.
    paddle_gpu = _paddle_gpu_build_installed()

    return (
        FrameworkCapabilities(
            torch_cuda=torch_cuda,
            torch_directml=directml,
            torch_mps=torch_mps,
            onnx_providers=providers,
            paddle_gpu=paddle_gpu,
        ),
        tuple(warnings),
    )
