"""Real-ESRGAN enhance model catalog: install, enable/disable, paths."""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from backend.models.reference.metadata import ExpectedFile
from backend.models.reference.catalog import (
    REALESRGAN_X2_ARTIFACT,
    REALESRGAN_X4_ARTIFACT,
)
from backend.tools.shared.constants import EnhanceMode
from backend.tools.shared.enabled_modes import EnabledModesCatalog
from backend.tools.shared import enabled_modes as _enabled_modes


@dataclass(frozen=True)
class EnhanceModelInfo:
    mode: EnhanceMode
    scale: int
    download_url: str
    version: str
    artifact: ExpectedFile
    """Recommended default (badge only; On/Off still works)."""
    is_default: bool = False


MODEL_CATALOG: List[EnhanceModelInfo] = [
    EnhanceModelInfo(
        EnhanceMode.X2PLUS,
        scale=2,
        download_url=(
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.2.1/RealESRGAN_x2plus.pth"
        ),
        version="v0.2.1",
        artifact=REALESRGAN_X2_ARTIFACT,
        is_default=True,
    ),
    EnhanceModelInfo(
        EnhanceMode.X4PLUS,
        scale=4,
        download_url=(
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.1.0/RealESRGAN_x4plus.pth"
        ),
        version="v0.1.0",
        artifact=REALESRGAN_X4_ARTIFACT,
        is_default=False,
    ),
]

_CATALOG_BY_MODE: Dict[EnhanceMode, EnhanceModelInfo] = {m.mode: m for m in MODEL_CATALOG}

DEFAULT_ENABLED_VALUES = tuple(m.mode.value for m in MODEL_CATALOG if m.is_default)


def models_dir() -> Path:
    from backend.core.paths import PATHS

    path = PATHS.models_dir / "realesrgan"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_file_path(mode: EnhanceMode) -> Path:
    return models_dir() / f"{mode.value}.pth"


def is_model_installed(mode: EnhanceMode) -> bool:
    path = model_file_path(mode)
    info = catalog_info(mode)
    try:
        return (
            info is not None
            and path.is_file()
            and path.stat().st_size == info.artifact.size_bytes
        )
    except OSError:
        return False


def verify_installed_model(mode: EnhanceMode) -> Path:
    """Return the weight path only when it matches the reviewed manifest."""
    from backend.models.artifacts import ArtifactVerificationError
    from backend.models.verifier import verify_file

    info = catalog_info(mode)
    if info is None:
        raise ValueError(f"Unknown enhance model: {mode}")
    result = verify_file(models_dir(), info.artifact)
    if not result.valid:
        raise ArtifactVerificationError(
            f"{mode.value} failed integrity verification: {result.reason}"
        )
    return result.path


def catalog_info(mode: EnhanceMode) -> Optional[EnhanceModelInfo]:
    return _CATALOG_BY_MODE.get(mode)


def native_scale(mode: EnhanceMode) -> int:
    info = catalog_info(mode)
    return info.scale if info else 2


_CATALOG = EnabledModesCatalog(
    mode_cls=EnhanceMode,
    catalog_modes=lambda: [info.mode for info in MODEL_CATALOG],
    default_enabled=DEFAULT_ENABLED_VALUES,
    is_installed=lambda mode: is_model_installed(mode),
    settings_section="enhancement",
    preferred_modes=(EnhanceMode.X2PLUS,),
)


def parse_enabled_values(raw: str) -> Set[str]:
    """Parse EnabledModels. Missing/blank → factory defaults; ``__none__`` → all Off."""
    return _enabled_modes.parse_enabled_values(_CATALOG, raw)


def serialize_enabled_values(values: Iterable[str]) -> str:
    return _enabled_modes.serialize_enabled_values(_CATALOG, values)


def get_enabled_values() -> Set[str]:
    return _enabled_modes.get_enabled_values(_CATALOG)


def set_model_enabled(mode: EnhanceMode, enabled: bool) -> None:
    """Turn a model On/Off for the Enhance dropdown (including the default)."""
    _enabled_modes.set_model_enabled(_CATALOG, mode, enabled)


def selectable_modes() -> List[EnhanceMode]:
    """Installed + On modes for the Enhance dropdown."""
    return _enabled_modes.selectable_modes(_CATALOG)


def ensure_selected_mode_valid() -> EnhanceMode:
    return _enabled_modes.ensure_selected_mode_valid(_CATALOG)


def apply_default_enhance_model() -> EnhanceMode:
    """Keep dropdown selection valid after install / On-Off changes."""
    return ensure_selected_mode_valid()


def discard_partial(mode: EnhanceMode) -> None:
    """Delete incomplete .pth.part so the next install starts over."""
    tmp = model_file_path(mode).with_suffix(".pth.part")
    try:
        if tmp.is_file():
            tmp.unlink()
    except OSError:
        pass


def uninstall_model(mode: EnhanceMode) -> None:
    """Delete local weights so the model can be reinstalled later."""
    if catalog_info(mode) is None:
        raise ValueError(f"Unknown enhance model: {mode}")
    dest = model_file_path(mode)
    discard_partial(mode)
    try:
        if dest.is_file():
            dest.unlink()
    except OSError as e:
        raise RuntimeError(f"Could not delete {dest}: {e}") from e
    set_model_enabled(mode, False)
    ensure_selected_mode_valid()


def install_model(mode: EnhanceMode) -> None:
    """Download .pth weights (blocking; call from a worker thread)."""
    from backend.tools.shared.download_registry import (
        KIND_ENHANCE,
        DownloadCancelled,
        ModelDownloadRegistry,
        urllib_cancel_reporthook,
    )

    info = catalog_info(mode)
    if info is None:
        raise ValueError(f"Unknown enhance model: {mode}")

    from backend.tools.shared.disk_preflight import ensure_disk_space

    ensure_disk_space(info.artifact.size_bytes or 0, context=mode.value)

    reg = ModelDownloadRegistry.instance()
    reg.begin(KIND_ENHANCE, mode.value)
    dest = model_file_path(mode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".pth.part")
    discard_partial(mode)

    try:
        from backend.models.artifacts import promote_verified_artifact

        reg.check_cancelled()
        urllib.request.urlretrieve(
            info.download_url, str(tmp), reporthook=urllib_cancel_reporthook
        )
        reg.check_cancelled()
        promote_verified_artifact(tmp, dest, info.artifact)
    except DownloadCancelled:
        discard_partial(mode)
        reg.fail(KIND_ENHANCE, mode.value, keep_pending=True)
        raise
    except Exception:
        discard_partial(mode)
        reg.fail(KIND_ENHANCE, mode.value, keep_pending=False)
        raise

    if not is_model_installed(mode):
        discard_partial(mode)
        reg.fail(KIND_ENHANCE, mode.value, keep_pending=False)
        raise RuntimeError(f"Download finished but model file missing: {dest}")
    set_model_enabled(mode, True)
    reg.complete(KIND_ENHANCE, mode.value)


def ensure_model_installed(mode: EnhanceMode) -> Path:
    """Install if missing (blocking). Returns weight path."""
    if not is_model_installed(mode):
        install_model(mode)
    return verify_installed_model(mode)
