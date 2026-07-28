"""MIRNet low-light model catalog: install, paths, enable/disable."""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from backend.tools.constant import LowLightMode

# Official LOL enhancement weights (swz30/MIRNet Google Drive).
_LOL_GDRIVE_ID = "1t_FcBuMZD5th2KWVVNXYGJ7bMz5ZAWvF"


@dataclass(frozen=True)
class LowLightModelInfo:
    mode: LowLightMode
    desc_key: str
    download_url: str
    is_default: bool = False


MODEL_CATALOG: List[LowLightModelInfo] = [
    LowLightModelInfo(
        LowLightMode.MIRNET_LOL,
        desc_key="MIRNET_LOL",
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
_NONE_ENABLED = "__none__"


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


def parse_enabled_values(raw: str) -> Set[str]:
    s = "" if raw is None else str(raw).strip()
    if not s:
        return set(DEFAULT_ENABLED_VALUES)
    if s == _NONE_ENABLED:
        return set()
    values = {part.strip() for part in s.split(",") if part.strip()}
    valid = {m.value for m in LowLightMode}
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

    return parse_enabled_values(config.lowLightEnabledModels.value)


def set_model_enabled(mode: LowLightMode, enabled: bool) -> None:
    from backend.config import config

    values = get_enabled_values()
    if enabled:
        values.add(mode.value)
    else:
        values.discard(mode.value)
    config.set(config.lowLightEnabledModels, serialize_enabled_values(values))


def selectable_modes() -> List[LowLightMode]:
    enabled = get_enabled_values()
    return [
        info.mode
        for info in MODEL_CATALOG
        if info.mode.value in enabled
        and (info.is_default or is_model_installed(info.mode))
    ]


def ensure_selected_mode_valid() -> LowLightMode:
    from backend.config import config

    current = config.lowLightMode.value
    available = selectable_modes()
    if current in available:
        return current
    if LowLightMode.MIRNET_LOL in available:
        config.set(config.lowLightMode, LowLightMode.MIRNET_LOL)
        return LowLightMode.MIRNET_LOL
    if available:
        config.set(config.lowLightMode, available[0])
        return available[0]
    return current


def apply_default_low_light_model() -> LowLightMode:
    return ensure_selected_mode_valid()


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
    except OSError as e:
        raise RuntimeError(f"Could not delete {dest}: {e}") from e
    set_model_enabled(mode, False)
    ensure_selected_mode_valid()


def install_model(mode: LowLightMode) -> None:
    """Download .pth weights (blocking; call from a worker thread)."""
    from backend.tools.model_download_registry import (
        KIND_LOW_LIGHT,
        DownloadCancelled,
        ModelDownloadRegistry,
        urllib_cancel_reporthook,
    )

    info = catalog_info(mode)
    if info is None:
        raise ValueError(f"Unknown low-light model: {mode}")

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
    set_model_enabled(mode, True)
    reg.complete(KIND_LOW_LIGHT, mode.value)


def ensure_model_installed(mode: LowLightMode) -> Path:
    """Install if missing (blocking). Always leaves the model On (Settings default)."""
    path = model_file_path(mode)
    if not is_model_installed(mode):
        install_model(mode)
    else:
        set_model_enabled(mode, True)
    return path
