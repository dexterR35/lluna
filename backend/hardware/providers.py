"""Optional framework capability probes; every probe is failure-isolated."""

from __future__ import annotations

import ctypes
import importlib.util
import os
import platform
from importlib import metadata
from pathlib import Path

from backend.hardware.profile import FrameworkCapabilities


_SUPPORTED_ONNX_PROVIDERS = frozenset(
    {
        "CPUExecutionProvider",
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "ROCMExecutionProvider",
        "MIGraphXExecutionProvider",
        "VitisAIExecutionProvider",
        "OpenVINOExecutionProvider",
        "MetalExecutionProvider",
        "CoreMLExecutionProvider",
    }
)
_WINDOWS_DLL_DIRECTORY_HANDLES: list[object] = []
_WINDOWS_DLL_DIRECTORIES: set[str] = set()


def _register_windows_cuda_dll_directories(site_packages: Path) -> None:
    """Expose framework-bundled CUDA DLLs to older ONNX Runtime builds."""
    if platform.system() != "Windows" or not hasattr(os, "add_dll_directory"):
        return
    directories = [
        site_packages / "torch" / "lib",
        site_packages / "paddle" / "libs",
    ]
    nvidia_root = site_packages / "nvidia"
    if nvidia_root.is_dir():
        directories.extend(sorted(nvidia_root.glob("*/bin")))

    for directory in directories:
        resolved = str(directory.resolve())
        if not directory.is_dir() or resolved in _WINDOWS_DLL_DIRECTORIES:
            continue
        try:
            handle = os.add_dll_directory(resolved)
        except OSError:
            continue
        # The handle must stay alive or Windows removes the directory again.
        _WINDOWS_DLL_DIRECTORY_HANDLES.append(handle)
        _WINDOWS_DLL_DIRECTORIES.add(resolved)


def _cuda_provider_library_ready(ort) -> bool:
    """Return whether ORT's CUDA provider and native dependencies can load."""
    system = platform.system()
    names = {
        "Windows": "onnxruntime_providers_cuda.dll",
        "Linux": "libonnxruntime_providers_cuda.so",
    }
    library_name = names.get(system)
    if library_name is None:
        return False

    module_file = getattr(ort, "__file__", None)
    if not module_file:
        # Test doubles and nonstandard ORT packages cannot be inspected here.
        return True
    package_dir = Path(module_file).resolve().parent
    if system == "Windows":
        _register_windows_cuda_dll_directories(package_dir.parent)
    library = package_dir / "capi" / library_name
    if not library.is_file():
        return False

    try:
        if system == "Windows":
            ctypes.WinDLL(str(library))
        else:
            ctypes.CDLL(str(library))
    except OSError:
        return False
    return True


def _usable_onnx_providers(
    ort, advertised: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Filter compiled-in providers to the subset Midgard can actually use."""
    usable: list[str] = []
    warnings: list[str] = []
    for provider in advertised:
        if provider not in _SUPPORTED_ONNX_PROVIDERS:
            warnings.append(f"Unsupported ONNX provider ignored: {provider}")
            continue
        if provider == "CUDAExecutionProvider" and not _cuda_provider_library_ready(ort):
            warnings.append(
                "ONNX CUDA provider ignored: its CUDA/cuDNN native dependencies "
                "could not be loaded"
            )
            continue
        usable.append(provider)
    if "CPUExecutionProvider" in advertised and "CPUExecutionProvider" not in usable:
        usable.append("CPUExecutionProvider")
    return tuple(usable), tuple(warnings)


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

        advertised = tuple(ort.get_available_providers())
        providers, provider_warnings = _usable_onnx_providers(ort, advertised)
        warnings.extend(provider_warnings)
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
