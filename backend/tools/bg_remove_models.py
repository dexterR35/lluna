"""Remove BG model catalog: detect installed ONNX weights, enable/disable, install."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from backend.tools.constant import BgRemoveMode


@dataclass(frozen=True)
class BgRemoveModelInfo:
    mode: BgRemoveMode
    category: str
    """Translation key under [BgRemoveModelDesc] for the short explanation."""
    desc_key: str
    """Recommended / category default (badge only; On/Off still works)."""
    is_default: bool = False


# Categories + one default each. Others are optional (install + on/off).
MODEL_CATALOG: List[BgRemoveModelInfo] = [
    # General / quality - BiRefNet General is the app default
    BgRemoveModelInfo(BgRemoveMode.BIREFNET, "General", "BIREFNET", True),
    BgRemoveModelInfo(BgRemoveMode.ISNET, "General", "ISNET", False),
    BgRemoveModelInfo(BgRemoveMode.U2NET, "General", "U2NET", False),
    BgRemoveModelInfo(BgRemoveMode.U2NETP, "General", "U2NETP", False),
    BgRemoveModelInfo(BgRemoveMode.SILUETA, "General", "SILUETA", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_LITE, "General", "BIREFNET_LITE", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_MASSIVE, "General", "BIREFNET_MASSIVE", False),
    BgRemoveModelInfo(BgRemoveMode.BRIA_RMBG, "General", "BRIA_RMBG", False),
    # People
    BgRemoveModelInfo(BgRemoveMode.U2NET_HUMAN, "People", "U2NET_HUMAN", True),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_PORTRAIT, "People", "BIREFNET_PORTRAIT", False),
    # Anime
    BgRemoveModelInfo(BgRemoveMode.ISNET_ANIME, "Anime", "ISNET_ANIME", True),
    # Clothes
    BgRemoveModelInfo(BgRemoveMode.U2NET_CLOTH, "Clothes", "U2NET_CLOTH", True),
    # Specialty
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_DIS, "Specialty", "BIREFNET_DIS", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_HRSOD, "Specialty", "BIREFNET_HRSOD", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_COD, "Specialty", "BIREFNET_COD", False),
]

_CATALOG_BY_MODE: Dict[BgRemoveMode, BgRemoveModelInfo] = {m.mode: m for m in MODEL_CATALOG}

DEFAULT_ENABLED_VALUES = tuple(
    m.mode.value for m in MODEL_CATALOG if m.is_default
)

# Saved when every model is Off (empty string would be read as “use factory defaults”)
_NONE_ENABLED = "__none__"


def u2net_home() -> Path:
    try:
        from rembg.sessions.base import BaseSession

        return Path(BaseSession.u2net_home()).expanduser()
    except Exception:
        return Path.home() / ".u2net"


def model_file_path(mode: BgRemoveMode) -> Path:
    return u2net_home() / f"{mode.value}.onnx"


def is_model_installed(mode: BgRemoveMode) -> bool:
    path = model_file_path(mode)
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def installed_modes() -> List[BgRemoveMode]:
    return [m.mode for m in MODEL_CATALOG if is_model_installed(m.mode)]


def catalog_info(mode: BgRemoveMode) -> Optional[BgRemoveModelInfo]:
    return _CATALOG_BY_MODE.get(mode)


def parse_enabled_values(raw: str) -> Set[str]:
    """Parse EnabledModels. Missing/blank → factory defaults; ``__none__`` → all Off."""
    s = "" if raw is None else str(raw).strip()
    if not s:
        return set(DEFAULT_ENABLED_VALUES)
    if s == _NONE_ENABLED:
        return set()
    values = {part.strip() for part in s.split(",") if part.strip()}
    valid = {m.value for m in BgRemoveMode}
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

    return parse_enabled_values(config.bgRemoveEnabledModels.value)


def set_model_enabled(mode: BgRemoveMode, enabled: bool) -> None:
    """Turn a model On/Off for the Run dropdown (any installed model, including defaults)."""
    from backend.config import config

    values = get_enabled_values()
    if enabled:
        values.add(mode.value)
    else:
        values.discard(mode.value)
    config.set(config.bgRemoveEnabledModels, serialize_enabled_values(values))


def selectable_modes() -> List[BgRemoveMode]:
    """Installed + On - what the Run dropdown may use."""
    enabled = get_enabled_values()
    return [
        info.mode
        for info in MODEL_CATALOG
        if is_model_installed(info.mode) and info.mode.value in enabled
    ]


def apply_default_bg_model() -> BgRemoveMode:
    """Keep dropdown selection valid after install / On-Off changes."""
    return ensure_selected_mode_valid()


def ensure_selected_mode_valid() -> BgRemoveMode:
    """If current config mode is missing/off, fall back to BiRefNet or first selectable."""
    from backend.config import config

    current = config.bgRemoveMode.value
    available = selectable_modes()
    if current in available:
        return current
    if BgRemoveMode.BIREFNET in available:
        config.set(config.bgRemoveMode, BgRemoveMode.BIREFNET)
        return BgRemoveMode.BIREFNET
    if available:
        config.set(config.bgRemoveMode, available[0])
        return available[0]
    return current


def install_model(mode: BgRemoveMode) -> None:
    """Download ONNX weights via rembg (blocking; call from a worker thread)."""
    try:
        from rembg.sessions import sessions_class
    except ImportError as e:
        raise ImportError(
            'rembg is not installed. Run: pip install "rembg[cpu]"  (or re-run install.py)'
        ) from e

    target = mode.value
    for cls in sessions_class:
        try:
            name = cls.name()
        except Exception:
            continue
        if name == target:
            cls.download_models()
            if not is_model_installed(mode):
                raise RuntimeError(f"Download finished but model file missing: {model_file_path(mode)}")
            # Newly installed defaults / optional: turn on so it appears in dropdown
            set_model_enabled(mode, True)
            return
    raise ValueError(f"Unknown rembg model: {target}")
