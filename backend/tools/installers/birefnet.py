"""BiRefNet model catalog, local snapshot, and isolated-runtime lifecycle.

BiRefNet's HF snapshots ship custom modeling code (BiRefNet_config.py,
birefnet.py, handler.py) that is loaded with ``trust_remote_code=True``.
Like SUPIR and SeedVR2, that code now runs inside its own pinned, isolated
venv instead of the main app's process/dependency environment, and its
download is pinned to a reviewed commit instead of tracking ``main``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from backend.core.atomic import atomic_write_text
from backend.core.paths import PATHS
from backend.tools.installers._shared import bootstrap_reviewed_python, create_isolated_venv

KIND_BIREFNET = "birefnet"
# Matches RUNTIME_PROFILES["birefnet-torch"].id in backend/models/reference/
# runtimes.py, whose runtime_installed() checks this exact
# model-runtimes/<id>/runtime.json path for isolated profiles.
BIREFNET_RUNTIME_PROFILE = "birefnet-torch"

MODEL_REPOS = {
    "birefnet": "ZhengPeng7/BiRefNet",
    "birefnet-dynamic": "ZhengPeng7/BiRefNet_dynamic",
    "birefnet-hr": "ZhengPeng7/BiRefNet_HR",
    "birefnet-hr-matting": "ZhengPeng7/BiRefNet_HR-matting",
    "birefnet-lite-2k": "ZhengPeng7/BiRefNet_lite-2K",
    "birefnet-matting": "ZhengPeng7/BiRefNet-matting",
}

# Pinned to each repo's current commit at review time, rather than tracking
# `main`, so the trust_remote_code modeling files that get executed can't
# change out from under an already-reviewed install.
MODEL_REVISIONS = {
    "birefnet": "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4",
    "birefnet-dynamic": "280306042f57b7a33854319da62fd86aaa89ec4c",
    "birefnet-hr": "a7a562f6fd16021180f2f4348f4de003a2d3d1e1",
    "birefnet-hr-matting": "5d6b6f8adcb5b417c871b1d84ceaae9871355b7f",
    "birefnet-lite-2k": "67d658fa863b1e716c3854270645e68860007d0e",
    "birefnet-matting": "57f9f68b43ba337c75762b14cf3075d659007268",
}

# Pinned from BiRefNet's own requirements.txt at MODEL_REVISIONS["birefnet"]
# (torch==2.5.1 there is upstream-mandated; the rest are Lluna-selected
# compatible versions, since upstream leaves them unpinned).
BIREFNET_PACKAGES = (
    "torch==2.5.1",
    "torchvision==0.20.1",
    "numpy==1.26.4",
    "opencv-python==4.10.0.84",
    "timm==1.0.11",
    "scipy==1.13.1",
    "scikit-image==0.24.0",
    "kornia==0.7.4",
    "einops==0.8.0",
    "tqdm",
    "prettytable==3.12.0",
    "transformers==4.46.3",
    "huggingface-hub==0.26.2",
    "accelerate==1.1.1",
    "pillow==10.4.0",
)


def models_root() -> Path:
    root = PATHS.models_dir / "birefnet"
    root.mkdir(parents=True, exist_ok=True)
    return root


def model_dir(model_id: str) -> Path:
    if model_id not in MODEL_REPOS:
        raise ValueError(f"Unknown BiRefNet model: {model_id}")
    return models_root() / model_id.removeprefix("birefnet-")


def runtime_dir() -> Path:
    return PATHS.data_dir / "model-runtimes" / BIREFNET_RUNTIME_PROFILE


def runtime_python() -> Path:
    return runtime_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def is_model_installed_at(path: Path) -> bool:
    return (path / "config.json").is_file() and bool(
        tuple(path.glob("*.safetensors")) + tuple(path.glob("*.bin"))
    )


def _runtime_ready() -> bool:
    return runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file()


def readiness(model_id: str) -> dict[str, bool]:
    return {
        "snapshot": is_model_installed_at(model_dir(model_id)),
        "runtime": _runtime_ready(),
    }


def is_model_installed(model_id: str) -> bool:
    status = readiness(model_id)
    return all(status.values())


def discard_partial(model_id: str) -> None:
    path = model_dir(model_id)
    for candidate in (path, path.with_name(f".{path.name}.staging")):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)


def _bootstrap_python() -> str:
    return bootstrap_reviewed_python(
        env_var="LLUNA_BIREFNET_PYTHON",
        versions=("3.11", "3.10", "3.12"),
        error_message=(
            "BiRefNet requires Python 3.10-3.12, and one could not be found or downloaded. "
            "Install one or point LLUNA_BIREFNET_PYTHON at an existing one."
        ),
        provision=True,
    )


def _install_runtime() -> None:
    if _runtime_ready():
        return
    python = _bootstrap_python()
    create_isolated_venv(
        python_executable=python,
        target_dir=runtime_dir(),
        staging_name=".birefnet-python.staging",
        pip_install_steps=[list(BIREFNET_PACKAGES)],
        runtime_metadata={
            "profile": BIREFNET_RUNTIME_PROFILE,
            "packages": list(BIREFNET_PACKAGES),
            "managedBy": "lluna",
        },
    )


def install_model(model_id: str) -> Path:
    """Download an official, revision-pinned HF snapshot and build the isolated runtime."""
    from backend.tools.shared.huggingface import snapshot_download_with_progress
    from backend.tools.shared.download_registry import (
        DownloadCancelled,
        ModelDownloadRegistry,
        download_progress_range,
    )

    if model_id not in MODEL_REPOS:
        raise ValueError(f"Unknown BiRefNet model: {model_id}")
    target = model_dir(model_id)
    staging = target.with_name(f".{target.name}.staging")
    registry = ModelDownloadRegistry.instance()
    registry.begin(KIND_BIREFNET, model_id)
    try:
        registry.check_cancelled()
        if not is_model_installed_at(target):
            discard_partial(model_id)
            shutil.rmtree(staging, ignore_errors=True)
            with download_progress_range(0, 70):
                snapshot_download_with_progress(
                    repo_id=MODEL_REPOS[model_id],
                    revision=MODEL_REVISIONS[model_id],
                    local_dir=str(staging),
                    allow_patterns=["*.json", "*.safetensors", "*.bin", "*.py", "*.txt"],
                )
            registry.check_cancelled()
            if not is_model_installed_at(staging):
                raise RuntimeError("BiRefNet download is incomplete: config.json and model weights are required.")
            marker = staging / ".lluna-installed"
            atomic_write_text(marker, f"{MODEL_REPOS[model_id]}@{MODEL_REVISIONS[model_id]}\n")
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            staging.replace(target)
        registry.check_cancelled()
        with download_progress_range(70, 100):
            _install_runtime()
        registry.complete(KIND_BIREFNET, model_id)
        return target
    except DownloadCancelled:
        shutil.rmtree(staging, ignore_errors=True)
        registry.fail(KIND_BIREFNET, model_id, keep_pending=True)
        raise
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        registry.fail(KIND_BIREFNET, model_id, keep_pending=False)
        raise


def uninstall_model(model_id: str) -> None:
    """Remove this model's snapshot, and the shared runtime if it was the last one."""
    discard_partial(model_id)
    if not any(is_model_installed_at(model_dir(item)) for item in MODEL_REPOS):
        shutil.rmtree(runtime_dir(), ignore_errors=True)
