"""FLUX.2 text-to-image model catalog: install, paths, enable/disable."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from backend.tools.constant import GenerateMode

_MARKER = ".midgard_installed"


@dataclass(frozen=True)
class GenerateModelInfo:
    mode: GenerateMode
    desc_key: str
    hf_repo: str
    pipeline: str
    default_guidance: float
    step_fast: int
    step_normal: int
    step_quality: int
    is_default: bool = False


MODEL_CATALOG: List[GenerateModelInfo] = [
    GenerateModelInfo(
        GenerateMode.FLUX2_KLEIN_4B,
        desc_key="FLUX2_KLEIN_4B",
        hf_repo="black-forest-labs/FLUX.2-klein-4B",
        pipeline="flux",
        default_guidance=1.0,
        step_fast=4,
        step_normal=8,
        step_quality=12,
        is_default=True,
    ),
    GenerateModelInfo(
        GenerateMode.FLUX2_KLEIN_9B,
        desc_key="FLUX2_KLEIN_9B",
        hf_repo="black-forest-labs/FLUX.2-klein-9B",
        pipeline="flux",
        default_guidance=1.0,
        step_fast=4,
        step_normal=8,
        step_quality=12,
        is_default=False,
    ),
    GenerateModelInfo(
        GenerateMode.SDXL_TURBO,
        desc_key="SDXL_TURBO",
        hf_repo="stabilityai/sdxl-turbo",
        pipeline="sdxl_turbo",
        default_guidance=0.0,
        step_fast=4,
        step_normal=8,
        step_quality=12,
        is_default=False,
    ),
    GenerateModelInfo(
        GenerateMode.SD15,
        desc_key="SD15",
        hf_repo="runwayml/stable-diffusion-v1-5",
        pipeline="sd15",
        default_guidance=7.5,
        step_fast=20,
        step_normal=28,
        step_quality=40,
        is_default=False,
    ),
]

_CATALOG_BY_MODE: Dict[GenerateMode, GenerateModelInfo] = {
    m.mode: m for m in MODEL_CATALOG
}

# Nothing On until the user installs (weights are large; Settings-only).
DEFAULT_ENABLED_VALUES: tuple[str, ...] = ()
_NONE_ENABLED = "__none__"


def models_dir() -> Path:
    from backend.config import BASE_DIR

    path = Path(BASE_DIR) / "models" / "generate"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_dir(mode: GenerateMode) -> Path:
    return models_dir() / mode.value


def is_model_installed(mode: GenerateMode) -> bool:
    path = model_dir(mode)
    marker = path / _MARKER
    if marker.is_file():
        return True
    # Adopt a complete local snapshot, but never while this mode is pending
    # (partial HF dirs often contain model_index.json early).
    if not (path / "model_index.json").is_file():
        return False
    try:
        from backend.tools.model_download_registry import (
            KIND_GENERATE,
            ModelDownloadRegistry,
        )

        pending = {
            p.key
            for p in ModelDownloadRegistry.instance().list_pending()
            if p.kind == KIND_GENERATE
        }
        if mode.value in pending:
            return False
    except Exception:
        pass
    try:
        marker.touch()
    except OSError:
        pass
    return True


def discard_partial(mode: GenerateMode) -> None:
    """Remove incomplete HF snapshot so the next install starts over."""
    import shutil

    dest = model_dir(mode)
    marker = dest / _MARKER
    if marker.is_file():
        return
    try:
        if dest.is_dir():
            shutil.rmtree(dest)
    except OSError:
        pass


def uninstall_model(mode: GenerateMode) -> None:
    """Delete local HF snapshot so the model can be reinstalled later."""
    import shutil

    if catalog_info(mode) is None:
        raise ValueError(f"Unknown generate model: {mode}")
    dest = model_dir(mode)
    try:
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()
    except OSError as e:
        raise RuntimeError(f"Could not delete {dest}: {e}") from e
    set_model_enabled(mode, False)
    ensure_selected_mode_valid()


def catalog_info(mode: GenerateMode) -> Optional[GenerateModelInfo]:
    return _CATALOG_BY_MODE.get(mode)


def parse_enabled_values(raw: str) -> Set[str]:
    s = "" if raw is None else str(raw).strip()
    if not s:
        return set(DEFAULT_ENABLED_VALUES)
    if s == _NONE_ENABLED:
        return set()
    values = {part.strip() for part in s.split(",") if part.strip()}
    valid = {m.value for m in GenerateMode}
    return {v for v in values if v in valid}


def serialize_enabled_values(values: Iterable[str]) -> str:
    ordered = []
    seen = set()
    for info in MODEL_CATALOG:
        v = info.mode.value
        if v in values and v not in seen:
            ordered.append(v)
            seen.add(v)
    return ",".join(ordered) if ordered else _NONE_ENABLED


def get_enabled_values() -> Set[str]:
    from backend.config import config

    return parse_enabled_values(config.generateEnabledModels.value)


def set_model_enabled(mode: GenerateMode, enabled: bool) -> None:
    from backend.config import config

    values = get_enabled_values()
    if enabled:
        values.add(mode.value)
    else:
        values.discard(mode.value)
    config.set(config.generateEnabledModels, serialize_enabled_values(values))


def selectable_modes() -> List[GenerateMode]:
    """On + installed only (no phantom defaults — weights must be on disk)."""
    enabled = get_enabled_values()
    return [
        info.mode
        for info in MODEL_CATALOG
        if info.mode.value in enabled and is_model_installed(info.mode)
    ]


def ensure_selected_mode_valid() -> GenerateMode:
    from backend.config import config

    current = config.generateMode.value
    available = selectable_modes()
    if current in available:
        return current
    if GenerateMode.FLUX2_KLEIN_4B in available:
        config.set(config.generateMode, GenerateMode.FLUX2_KLEIN_4B)
        return GenerateMode.FLUX2_KLEIN_4B
    if available:
        config.set(config.generateMode, available[0])
        return available[0]
    return current


def apply_default_generate_model() -> GenerateMode:
    return ensure_selected_mode_valid()


def install_model(mode: GenerateMode) -> Path:
    """Download HF Diffusers weights (blocking; call from a worker thread)."""
    from backend.tools.model_download_registry import (
        KIND_GENERATE,
        DownloadCancelled,
        ModelDownloadRegistry,
    )

    info = catalog_info(mode)
    if info is None:
        raise ValueError(f"Unknown generate model: {mode}")

    reg = ModelDownloadRegistry.instance()
    dest = model_dir(mode)
    if is_model_installed(mode):
        set_model_enabled(mode, True)
        reg.complete(KIND_GENERATE, mode.value)
        return dest

    reg.begin(KIND_GENERATE, mode.value)
    discard_partial(mode)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        reg.fail(KIND_GENERATE, mode.value, keep_pending=False)
        raise RuntimeError(
            "huggingface_hub is required for Generate models. "
            "Re-run install.py or pip install huggingface_hub."
        ) from e

    from backend.tools.hf_auth import apply_hf_token_to_env, snapshot_download_kwargs

    apply_hf_token_to_env()
    try:
        reg.check_cancelled()
        snapshot_download(
            repo_id=info.hf_repo,
            local_dir=str(dest),
            local_dir_use_symlinks=False,
            **snapshot_download_kwargs(),
        )
        reg.check_cancelled()
    except DownloadCancelled:
        discard_partial(mode)
        reg.fail(KIND_GENERATE, mode.value, keep_pending=True)
        raise
    except Exception as e:
        discard_partial(mode)
        reg.fail(KIND_GENERATE, mode.value, keep_pending=False)
        msg = str(e)
        lower = msg.lower()
        if "401" in msg or "403" in msg or "gated" in lower or "unauthorized" in lower:
            raise RuntimeError(
                f"{msg}\n\n"
                "This Hugging Face repo may be gated or rate-limited. "
                "Set a read token in Settings → Generate Models (or export HF_TOKEN), "
                "and accept the model license on huggingface.co."
            ) from e
        raise
    (dest / _MARKER).touch()

    if not is_model_installed(mode):
        discard_partial(mode)
        reg.fail(KIND_GENERATE, mode.value, keep_pending=False)
        raise RuntimeError(f"Download finished but model missing: {dest}")
    set_model_enabled(mode, True)
    reg.complete(KIND_GENERATE, mode.value)
    return dest


def ensure_model_installed(mode: GenerateMode) -> Path:
    """Install if missing (blocking). Always leaves the model On."""
    path = model_dir(mode)
    if not is_model_installed(mode):
        install_model(mode)
    else:
        set_model_enabled(mode, True)
    return path


def local_repo_path(mode: GenerateMode) -> Path:
    path = model_dir(mode)
    if not is_model_installed(mode):
        raise FileNotFoundError(f"Generate model not installed: {mode.value}")
    return path


def cuda_ready_for_generate() -> tuple[bool, str]:
    """Hard gate: CUDA must exist and accept a tiny tensor (no CPU fallback)."""
    try:
        import torch
    except ImportError:
        return False, "PyTorch is not installed."

    if not torch.cuda.is_available():
        return False, "No NVIDIA CUDA GPU detected. Generate requires CUDA."

    from backend.config import config
    from backend.tools.hardware_accelerator import HardwareAccelerator

    hw = HardwareAccelerator.instance()
    hw.set_enabled(bool(config.hardwareAcceleration.value))
    if not hw.has_cuda():
        return False, (
            "Hardware acceleration is off or CUDA is unavailable. "
            "Turn on Hardware Acceleration in Settings, then retry."
        )

    try:
        t = torch.zeros(1, device="cuda")
        del t
        torch.cuda.synchronize()
    except Exception as e:
        return False, f"CUDA is present but not working: {e}"

    return True, ""
