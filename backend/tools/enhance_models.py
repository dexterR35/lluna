"""Real-ESRGAN enhance model catalog: install, enable/disable, paths."""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from backend.tools.constant import EnhanceMode


@dataclass(frozen=True)
class EnhanceModelInfo:
    mode: EnhanceMode
    scale: int
    """Translation key under [EnhanceMode] / [EnhanceModelDesc]."""
    desc_key: str
    download_url: str
    """Recommended default (badge only; On/Off still works)."""
    is_default: bool = False


MODEL_CATALOG: List[EnhanceModelInfo] = [
    EnhanceModelInfo(
        EnhanceMode.X2PLUS,
        scale=2,
        desc_key="X2PLUS",
        download_url=(
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.2.1/RealESRGAN_x2plus.pth"
        ),
        is_default=True,
    ),
    EnhanceModelInfo(
        EnhanceMode.X4PLUS,
        scale=4,
        desc_key="X4PLUS",
        download_url=(
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.1.0/RealESRGAN_x4plus.pth"
        ),
        is_default=False,
    ),
]

_CATALOG_BY_MODE: Dict[EnhanceMode, EnhanceModelInfo] = {m.mode: m for m in MODEL_CATALOG}

DEFAULT_ENABLED_VALUES = tuple(m.mode.value for m in MODEL_CATALOG if m.is_default)

# Saved when every model is Off (empty string would be read as “use factory defaults”)
_NONE_ENABLED = "__none__"


def models_dir() -> Path:
    from backend.config import BASE_DIR

    path = Path(BASE_DIR) / "models" / "realesrgan"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_file_path(mode: EnhanceMode) -> Path:
    return models_dir() / f"{mode.value}.pth"


def is_model_installed(mode: EnhanceMode) -> bool:
    path = model_file_path(mode)
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def catalog_info(mode: EnhanceMode) -> Optional[EnhanceModelInfo]:
    return _CATALOG_BY_MODE.get(mode)


def native_scale(mode: EnhanceMode) -> int:
    info = catalog_info(mode)
    return info.scale if info else 2


def parse_enabled_values(raw: str) -> Set[str]:
    """Parse EnabledModels. Missing/blank → factory defaults; ``__none__`` → all Off."""
    s = "" if raw is None else str(raw).strip()
    if not s:
        return set(DEFAULT_ENABLED_VALUES)
    if s == _NONE_ENABLED:
        return set()
    values = {part.strip() for part in s.split(",") if part.strip()}
    valid = {m.value for m in EnhanceMode}
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

    return parse_enabled_values(config.enhanceEnabledModels.value)


def set_model_enabled(mode: EnhanceMode, enabled: bool) -> None:
    """Turn a model On/Off for the Enhance dropdown (including the default)."""
    from backend.config import config

    values = get_enabled_values()
    if enabled:
        values.add(mode.value)
    else:
        values.discard(mode.value)
    config.set(config.enhanceEnabledModels, serialize_enabled_values(values))


def selectable_modes() -> List[EnhanceMode]:
    """On + available modes for the Enhance dropdown.

    Default (x2plus) can appear before first download when On; optional
    models (x4plus) require install + On.
    """
    enabled = get_enabled_values()
    return [
        info.mode
        for info in MODEL_CATALOG
        if info.mode.value in enabled
        and (info.is_default or is_model_installed(info.mode))
    ]


def ensure_selected_mode_valid() -> EnhanceMode:
    from backend.config import config

    current = config.enhanceMode.value
    available = selectable_modes()
    if current in available:
        return current
    if EnhanceMode.X2PLUS in available:
        config.set(config.enhanceMode, EnhanceMode.X2PLUS)
        return EnhanceMode.X2PLUS
    if available:
        config.set(config.enhanceMode, available[0])
        return available[0]
    return current


def apply_default_enhance_model() -> EnhanceMode:
    """Keep dropdown selection valid after install / On-Off changes."""
    return ensure_selected_mode_valid()


def install_model(mode: EnhanceMode) -> None:
    """Download .pth weights (blocking; call from a worker thread)."""
    info = catalog_info(mode)
    if info is None:
        raise ValueError(f"Unknown enhance model: {mode}")

    dest = model_file_path(mode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".pth.part")

    try:
        urllib.request.urlretrieve(info.download_url, str(tmp))
        if not tmp.is_file() or tmp.stat().st_size <= 0:
            raise RuntimeError(f"Download finished but file empty: {tmp}")
        os.replace(str(tmp), str(dest))
    except Exception:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        raise

    if not is_model_installed(mode):
        raise RuntimeError(f"Download finished but model file missing: {dest}")
    set_model_enabled(mode, True)


def ensure_model_installed(mode: EnhanceMode) -> Path:
    """Install if missing (blocking). Returns weight path."""
    path = model_file_path(mode)
    if not is_model_installed(mode):
        install_model(mode)
    return path
