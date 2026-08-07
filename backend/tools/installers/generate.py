"""Diffusers text-to-image model catalog: install, paths, enable/disable."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from backend.tools.shared.constants import GenerateMode
from backend.tools.shared.enabled_modes import EnabledModesCatalog
from backend.tools.shared import enabled_modes as _enabled_modes

_MARKER = ".lluna_installed"

_DIFFUSERS_ALLOW_PATTERNS = (
    "model_index.json",
    "scheduler/*.json",
    "text_encoder/*.json",
    "text_encoder/*.safetensors",
    "tokenizer/*",
    "transformer/*.json",
    "transformer/*.safetensors",
    "vae/*.json",
    "vae/*.safetensors",
)


_FLUX2_KLEIN_FP8_COMPONENT_PATTERNS = (
    "model_index.json",
    "scheduler/*.json",
    "text_encoder/*.json",
    "text_encoder/*.safetensors",
    "tokenizer/*",
    "transformer/config.json",
    "vae/*.json",
    "vae/*.safetensors",
)


@dataclass(frozen=True)
class GenerateDownload:
    hf_repo: str
    allow_patterns: tuple[str, ...]


@dataclass(frozen=True)
class GenerateModelInfo:
    mode: GenerateMode
    hf_repo: str
    pipeline: str
    default_guidance: float
    download_allow_patterns: tuple[str, ...]
    supporting_downloads: tuple[GenerateDownload, ...] = ()
    single_file_name: Optional[str] = None
    sequential_cpu_offload: bool = False
    is_default: bool = False


MODEL_CATALOG: List[GenerateModelInfo] = [
    GenerateModelInfo(
        GenerateMode.FLUX2_KLEIN_4B,
        hf_repo="black-forest-labs/FLUX.2-klein-4B",
        pipeline="flux2_klein",
        default_guidance=1.0,
        download_allow_patterns=_DIFFUSERS_ALLOW_PATTERNS,
        is_default=False,
    ),
    GenerateModelInfo(
        GenerateMode.FLUX2_KLEIN_9B,
        hf_repo="black-forest-labs/FLUX.2-klein-9B",
        pipeline="flux2_klein",
        default_guidance=1.0,
        download_allow_patterns=_DIFFUSERS_ALLOW_PATTERNS,
        is_default=False,
    ),
    GenerateModelInfo(
        GenerateMode.FLUX2_KLEIN_BASE_4B,
        hf_repo="black-forest-labs/FLUX.2-klein-base-4B",
        pipeline="flux2_klein",
        default_guidance=4.0,
        download_allow_patterns=_DIFFUSERS_ALLOW_PATTERNS,
        is_default=True,
    ),
    GenerateModelInfo(
        GenerateMode.FLUX2_KLEIN_BASE_9B,
        hf_repo="black-forest-labs/FLUX.2-klein-base-9B",
        pipeline="flux2_klein",
        default_guidance=4.0,
        download_allow_patterns=_DIFFUSERS_ALLOW_PATTERNS,
        is_default=False,
    ),
    GenerateModelInfo(
        GenerateMode.FLUX2_DEV,
        hf_repo="black-forest-labs/FLUX.2-dev",
        pipeline="flux2",
        default_guidance=4.0,
        download_allow_patterns=_DIFFUSERS_ALLOW_PATTERNS,
        sequential_cpu_offload=True,
        is_default=False,
    ),
    GenerateModelInfo(
        GenerateMode.FLUX2_KLEIN_9B_FP8,
        hf_repo="black-forest-labs/FLUX.2-klein-9b-fp8",
        pipeline="flux2_klein_fp8",
        default_guidance=1.0,
        download_allow_patterns=("flux-2-klein-9b-fp8.safetensors",),
        supporting_downloads=(
            GenerateDownload(
                "black-forest-labs/FLUX.2-klein-9B",
                _FLUX2_KLEIN_FP8_COMPONENT_PATTERNS,
            ),
        ),
        single_file_name="flux-2-klein-9b-fp8.safetensors",
        sequential_cpu_offload=True,
        is_default=False,
    ),
    GenerateModelInfo(
        GenerateMode.QWEN_IMAGE,
        hf_repo="Qwen/Qwen-Image",
        pipeline="qwen_image",
        default_guidance=4.0,
        download_allow_patterns=_DIFFUSERS_ALLOW_PATTERNS,
        sequential_cpu_offload=True,
        is_default=False,
    ),
]

_CATALOG_BY_MODE: Dict[GenerateMode, GenerateModelInfo] = {m.mode: m for m in MODEL_CATALOG}

# Nothing On until the user installs (weights are large; Settings-only).
DEFAULT_ENABLED_VALUES: tuple[str, ...] = ()


def models_dir() -> Path:
    from backend.core.paths import PATHS

    path = PATHS.models_dir / "generate"
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
        from backend.tools.shared.download_registry import (
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

    info = catalog_info(mode)
    if info is None:
        raise ValueError(f"Unknown generate model: {mode}")
    from backend.tools.shared.huggingface import remove_hf_repo_cache

    # Older releases kept a second copy in the shared Hugging Face cache.
    for download in model_downloads(info):
        remove_hf_repo_cache(download.hf_repo)
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


def model_downloads(info: GenerateModelInfo) -> tuple[GenerateDownload, ...]:
    return (
        GenerateDownload(info.hf_repo, info.download_allow_patterns),
        *info.supporting_downloads,
    )


def _validate_download_snapshot(info: GenerateModelInfo, dest: Path) -> None:
    from backend.tools.shared.huggingface import require_snapshot_files

    required_files = [
        "model_index.json",
        "scheduler/scheduler_config.json",
        "text_encoder/config.json",
        "tokenizer/tokenizer_config.json",
        "vae/config.json",
        "transformer/config.json",
    ]
    required_glob_dirs = {"text_encoder": "*.safetensors", "vae": "*.safetensors"}
    if info.single_file_name:
        required_files.append(info.single_file_name)
    else:
        required_glob_dirs["transformer"] = "*.safetensors"

    require_snapshot_files(
        dest, required_files, name=info.mode.value, required_glob_dirs=required_glob_dirs
    )


_CATALOG = EnabledModesCatalog(
    mode_cls=GenerateMode,
    catalog_modes=lambda: [info.mode for info in MODEL_CATALOG],
    default_enabled=DEFAULT_ENABLED_VALUES,
    is_installed=lambda mode: is_model_installed(mode),
    settings_section="generation",
    preferred_modes=(GenerateMode.FLUX2_KLEIN_BASE_4B,),
)


def parse_enabled_values(raw: str) -> Set[str]:
    return _enabled_modes.parse_enabled_values(_CATALOG, raw)


def serialize_enabled_values(values: Iterable[str]) -> str:
    return _enabled_modes.serialize_enabled_values(_CATALOG, values)


def get_enabled_values() -> Set[str]:
    return _enabled_modes.get_enabled_values(_CATALOG)


def set_model_enabled(mode: GenerateMode, enabled: bool) -> None:
    _enabled_modes.set_model_enabled(_CATALOG, mode, enabled)


def selectable_modes() -> List[GenerateMode]:
    """On + installed only (no phantom defaults — weights must be on disk)."""
    return _enabled_modes.selectable_modes(_CATALOG)


def ensure_selected_mode_valid() -> GenerateMode:
    return _enabled_modes.ensure_selected_mode_valid(_CATALOG)


def apply_default_generate_model() -> GenerateMode:
    return ensure_selected_mode_valid()


def install_model(mode: GenerateMode) -> Path:
    """Download HF Diffusers weights (blocking; call from a worker thread)."""
    from backend.tools.shared.download_registry import (
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
        import huggingface_hub  # noqa: F401
    except ImportError as e:
        reg.fail(KIND_GENERATE, mode.value, keep_pending=False)
        raise RuntimeError(
            "huggingface_hub is required for Generate models. "
            "Re-run install.py or pip install huggingface_hub."
        ) from e

    from backend.tools.shared.huggingface import (
        apply_hf_token_to_env,
        remove_hf_repo_cache,
        snapshot_download_with_progress,
    )

    apply_hf_token_to_env()
    try:
        reg.check_cancelled()
        for download in model_downloads(info):
            snapshot_download_with_progress(
                repo_id=download.hf_repo,
                local_dir=str(dest),
                allow_patterns=list(download.allow_patterns),
            )
            reg.check_cancelled()
        _validate_download_snapshot(info, dest)
        # The runtime snapshot is complete; its download cache is redundant.
        for download in model_downloads(info):
            remove_hf_repo_cache(download.hf_repo, include_shared=False)
    except DownloadCancelled:
        discard_partial(mode)
        reg.fail(KIND_GENERATE, mode.value, keep_pending=True)
        for download in model_downloads(info):
            try:
                remove_hf_repo_cache(download.hf_repo, include_shared=False)
            except Exception:
                pass
        raise
    except Exception as e:
        discard_partial(mode)
        reg.fail(KIND_GENERATE, mode.value, keep_pending=False)
        for download in model_downloads(info):
            try:
                remove_hf_repo_cache(download.hf_repo, include_shared=False)
            except Exception:
                pass
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

    from backend.configuration.service import get_settings
    from backend.tools.shared.hardware import HardwareAccelerator

    hw = HardwareAccelerator.instance()
    hw.set_enabled(bool(get_settings().subtitle.hardware_acceleration))
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
