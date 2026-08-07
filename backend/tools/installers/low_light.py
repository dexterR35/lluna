"""MIRNet low-light model catalog: install, paths, enable/disable."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from backend.tools.shared.constants import LowLightMode
from backend.tools.shared.enabled_modes import EnabledModesCatalog
from backend.tools.shared import enabled_modes as _enabled_modes

# Official LOL enhancement weights (swz30/MIRNet Google Drive).
_LOL_GDRIVE_ID = "1t_FcBuMZD5th2KWVVNXYGJ7bMz5ZAWvF"
# Google Drive doesn't report a size before downloading; the real file is
# ~120MB+ (see is_model_installed's size floor below), so this is a
# generous round-up used only for the disk-space preflight check.
_APPROX_DOWNLOAD_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class LowLightModelInfo:
    mode: LowLightMode
    download_url: str
    is_default: bool = False


MODEL_CATALOG: List[LowLightModelInfo] = [
    LowLightModelInfo(
        LowLightMode.MIRNET_LOL,
        download_url=(
            "https://drive.usercontent.google.com/download"
            f"?id={_LOL_GDRIVE_ID}&export=download&confirm=t"
        ),
        is_default=True,
    ),
]

_CATALOG_BY_MODE: Dict[LowLightMode, LowLightModelInfo] = {
    m.mode: m for m in MODEL_CATALOG
}

DEFAULT_ENABLED_VALUES = tuple(m.mode.value for m in MODEL_CATALOG if m.is_default)


def models_dir() -> Path:
    from backend.core.paths import PATHS

    path = PATHS.models_dir / "mirnet"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_file_path(mode: LowLightMode) -> Path:
    return models_dir() / f"{mode.value}.pth"


def is_model_installed(mode: LowLightMode) -> bool:
    path = model_file_path(mode)
    try:
        # Official LOL weights are ~120MB+; reject HTML error pages.
        return path.is_file() and path.stat().st_size > 1_000_000
    except OSError:
        return False


def catalog_info(mode: LowLightMode) -> Optional[LowLightModelInfo]:
    return _CATALOG_BY_MODE.get(mode)


_CATALOG = EnabledModesCatalog(
    mode_cls=LowLightMode,
    catalog_modes=lambda: [info.mode for info in MODEL_CATALOG],
    default_enabled=DEFAULT_ENABLED_VALUES,
    is_installed=lambda mode: is_model_installed(mode),
    settings_section="low_light",
    preferred_modes=(LowLightMode.MIRNET_LOL,),
)


def parse_enabled_values(raw: str) -> Set[str]:
    return _enabled_modes.parse_enabled_values(_CATALOG, raw)


def serialize_enabled_values(values: Iterable[str]) -> str:
    return _enabled_modes.serialize_enabled_values(_CATALOG, values)


def get_enabled_values() -> Set[str]:
    return _enabled_modes.get_enabled_values(_CATALOG)


def set_model_enabled(mode: LowLightMode, enabled: bool) -> None:
    _enabled_modes.set_model_enabled(_CATALOG, mode, enabled)


def selectable_modes() -> List[LowLightMode]:
    return _enabled_modes.selectable_modes(_CATALOG)


def ensure_selected_mode_valid() -> LowLightMode:
    return _enabled_modes.ensure_selected_mode_valid(_CATALOG)


def apply_default_low_light_model() -> LowLightMode:
    return ensure_selected_mode_valid()


def _integrity_sidecar_path(mode: LowLightMode) -> Path:
    return model_file_path(mode).with_suffix(".pth.integrity.json")


def _record_integrity(mode: LowLightMode, path: Path) -> None:
    """Pin the downloaded weight's SHA-256 on first successful install.

    The upstream source is a third-party Google Drive mirror, not an
    official pinned release with a reviewed-in-advance hash (unlike
    Real-ESRGAN's GitHub releases), so there is nothing to check the very
    first download against. This is trust-on-first-use: the pin only
    protects against corruption or on-disk tampering *after* install, not a
    compromised first download.
    """
    from backend.core.atomic import atomic_write_json

    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    atomic_write_json(
        _integrity_sidecar_path(mode),
        {"size_bytes": path.stat().st_size, "sha256": hasher.hexdigest()},
    )


def verify_installed_model(mode: LowLightMode) -> Path:
    """Return the weight path only when it matches the pinned SHA-256, if any."""
    from backend.models.artifacts import ArtifactVerificationError
    from backend.models.reference.metadata import ExpectedFile
    from backend.models.verifier import verify_file

    path = model_file_path(mode)
    sidecar = _integrity_sidecar_path(mode)
    if not sidecar.is_file():
        # Pre-existing install from before integrity pinning was added;
        # nothing pinned yet to check against.
        return path
    pinned = json.loads(sidecar.read_text(encoding="utf-8"))
    expected = ExpectedFile(
        relative_path=path.name,
        size_bytes=pinned.get("size_bytes"),
        sha256=pinned.get("sha256"),
    )
    result = verify_file(models_dir(), expected)
    if not result.valid:
        raise ArtifactVerificationError(
            f"{mode.value} failed integrity verification: {result.reason}"
        )
    return path


def discard_partial(mode: LowLightMode) -> None:
    """Delete incomplete .pth.part so the next install starts over."""
    tmp = model_file_path(mode).with_suffix(".pth.part")
    try:
        if tmp.is_file():
            tmp.unlink()
    except OSError:
        pass


def uninstall_model(mode: LowLightMode) -> None:
    """Delete local weights so the model can be reinstalled later."""
    if catalog_info(mode) is None:
        raise ValueError(f"Unknown low-light model: {mode}")
    dest = model_file_path(mode)
    discard_partial(mode)
    try:
        if dest.is_file():
            dest.unlink()
        _integrity_sidecar_path(mode).unlink(missing_ok=True)
    except OSError as e:
        raise RuntimeError(f"Could not delete {dest}: {e}") from e
    set_model_enabled(mode, False)
    ensure_selected_mode_valid()


def install_model(mode: LowLightMode) -> None:
    """Download .pth weights (blocking; call from a worker thread)."""
    from backend.tools.shared.download_registry import (
        KIND_LOW_LIGHT,
        DownloadCancelled,
        ModelDownloadRegistry,
        urllib_cancel_reporthook,
    )

    info = catalog_info(mode)
    if info is None:
        raise ValueError(f"Unknown low-light model: {mode}")

    from backend.tools.shared.disk_preflight import ensure_disk_space

    ensure_disk_space(_APPROX_DOWNLOAD_BYTES, context=mode.value)

    reg = ModelDownloadRegistry.instance()
    reg.begin(KIND_LOW_LIGHT, mode.value)
    dest = model_file_path(mode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".pth.part")
    discard_partial(mode)

    try:
        reg.check_cancelled()
        urllib.request.urlretrieve(
            info.download_url, str(tmp), reporthook=urllib_cancel_reporthook
        )
        reg.check_cancelled()
        if not tmp.is_file() or tmp.stat().st_size <= 1_000_000:
            raise RuntimeError(
                "Download finished but file looks invalid "
                f"(size={tmp.stat().st_size if tmp.is_file() else 0}). "
                "Try again or install from Settings."
            )
        # Reject HTML interstitial pages mistakenly saved as .pth
        with open(tmp, "rb") as f:
            head = f.read(32)
        if head.lstrip().startswith((b"<", b"<!")):
            raise RuntimeError(
                "Download returned an HTML page instead of MIRNet weights. "
                "Try again later or download model_lol.pth manually."
            )
        os.replace(str(tmp), str(dest))
    except DownloadCancelled:
        discard_partial(mode)
        reg.fail(KIND_LOW_LIGHT, mode.value, keep_pending=True)
        raise
    except Exception:
        discard_partial(mode)
        reg.fail(KIND_LOW_LIGHT, mode.value, keep_pending=False)
        raise

    if not is_model_installed(mode):
        discard_partial(mode)
        reg.fail(KIND_LOW_LIGHT, mode.value, keep_pending=False)
        raise RuntimeError(f"Download finished but model file missing: {dest}")
    _record_integrity(mode, dest)
    set_model_enabled(mode, True)
    reg.complete(KIND_LOW_LIGHT, mode.value)


def ensure_model_installed(mode: LowLightMode) -> Path:
    """Install if missing (blocking). Always leaves the model On (Settings default)."""
    if not is_model_installed(mode):
        install_model(mode)
    else:
        set_model_enabled(mode, True)
    return verify_installed_model(mode)
