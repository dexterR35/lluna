"""BiRefNet model catalog and local snapshot lifecycle."""

from __future__ import annotations

import shutil
from pathlib import Path

from backend.core.atomic import atomic_write_text

KIND_BIREFNET = "birefnet"

MODEL_REPOS = {
    "birefnet": "zhengpeng7/BiRefNet",
    "birefnet-dynamic": "zhengpeng7/BiRefNet_dynamic",
    "birefnet-hr": "zhengpeng7/BiRefNet_HR",
    "birefnet-hr-matting": "zhengpeng7/BiRefNet_HR-matting",
    "birefnet-lite-2k": "zhengpeng7/BiRefNet_lite-2K",
    "birefnet-matting": "zhengpeng7/BiRefNet-matting",
}


def models_root() -> Path:
    from backend.core.paths import PATHS

    root = PATHS.models_dir / "birefnet"
    root.mkdir(parents=True, exist_ok=True)
    return root


def model_dir(model_id: str) -> Path:
    if model_id not in MODEL_REPOS:
        raise ValueError(f"Unknown BiRefNet model: {model_id}")
    return models_root() / model_id.removeprefix("birefnet-")


def is_model_installed(model_id: str) -> bool:
    path = model_dir(model_id)
    if not (path / "config.json").is_file():
        return False
    weights = tuple(path.glob("*.safetensors")) + tuple(path.glob("*.bin"))
    return bool(weights)


def discard_partial(model_id: str) -> None:
    path = model_dir(model_id)
    for candidate in (path, path.with_name(f".{path.name}.staging")):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)


def install_model(model_id: str) -> Path:
    """Download an official HF snapshot into a replaceable managed folder."""
    from backend.tools.hf_auth import snapshot_download_with_progress
    from backend.tools.model_download_registry import (
        DownloadCancelled,
        ModelDownloadRegistry,
        download_progress_range,
    )

    target = model_dir(model_id)
    staging = target.with_name(f".{target.name}.staging")
    discard_partial(model_id)
    shutil.rmtree(staging, ignore_errors=True)
    registry = ModelDownloadRegistry.instance()
    registry.begin(KIND_BIREFNET, model_id)
    try:
        registry.check_cancelled()
        with download_progress_range(0, 95):
            snapshot_download_with_progress(
                repo_id=MODEL_REPOS[model_id],
                local_dir=str(staging),
                allow_patterns=["*.json", "*.safetensors", "*.bin", "*.py", "*.txt"],
            )
        registry.check_cancelled()
        if not is_model_installed_at(staging):
            raise RuntimeError("BiRefNet download is incomplete: config.json and model weights are required.")
        marker = staging / ".midgard-installed"
        atomic_write_text(marker, f"{MODEL_REPOS[model_id]}\n")
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
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


def is_model_installed_at(path: Path) -> bool:
    return (path / "config.json").is_file() and bool(
        tuple(path.glob("*.safetensors")) + tuple(path.glob("*.bin"))
    )
