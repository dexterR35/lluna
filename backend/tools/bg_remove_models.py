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
    """Recommended / category default (badge only; On/Off still works)."""
    is_default: bool = False


# Categories + one default each. Others are optional (install + on/off).
MODEL_CATALOG: List[BgRemoveModelInfo] = [
    # General / quality - BiRefNet General is the app default
    BgRemoveModelInfo(BgRemoveMode.BIREFNET, "General", True),
    BgRemoveModelInfo(BgRemoveMode.ISNET, "General", False),
    BgRemoveModelInfo(BgRemoveMode.U2NET, "General", False),
    BgRemoveModelInfo(BgRemoveMode.U2NETP, "General", False),
    BgRemoveModelInfo(BgRemoveMode.SILUETA, "General", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_LITE, "General", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_MASSIVE, "General", False),
    BgRemoveModelInfo(BgRemoveMode.BRIA_RMBG, "General", False),
    # People
    BgRemoveModelInfo(BgRemoveMode.U2NET_HUMAN, "People", True),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_PORTRAIT, "People", False),
    # Anime
    BgRemoveModelInfo(BgRemoveMode.ISNET_ANIME, "Anime", True),
    # Clothes
    BgRemoveModelInfo(BgRemoveMode.U2NET_CLOTH, "Clothes", True),
    # Specialty
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_DIS, "Specialty", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_HRSOD, "Specialty", False),
    BgRemoveModelInfo(BgRemoveMode.BIREFNET_COD, "Specialty", False),
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
    from backend.configuration.service import get_settings

    return parse_enabled_values(get_settings().background_removal.enabled_models)


def set_model_enabled(mode: BgRemoveMode, enabled: bool) -> None:
    """Turn a model On/Off for the Run dropdown (any installed model, including defaults)."""
    from backend.configuration.service import update_settings

    values = get_enabled_values()
    if enabled:
        values.add(mode.value)
    else:
        values.discard(mode.value)
    update_settings({"background_removal": {"enabled_models": serialize_enabled_values(values)}})


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
    from backend.configuration.service import get_settings, update_settings

    current = BgRemoveMode(get_settings().background_removal.mode)
    available = selectable_modes()
    if current in available:
        return current
    if BgRemoveMode.BIREFNET in available:
        update_settings({"background_removal": {"mode": BgRemoveMode.BIREFNET.value}})
        return BgRemoveMode.BIREFNET
    if available:
        update_settings({"background_removal": {"mode": available[0].value}})
        return available[0]
    return current


def discard_partial(mode: BgRemoveMode) -> None:
    """Remove ONNX so a cancelled / interrupted install starts over."""
    path = model_file_path(mode)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def uninstall_model(mode: BgRemoveMode) -> None:
    """Delete local ONNX weights so the model can be reinstalled later."""
    from backend.tools import diag

    if catalog_info(mode) is None:
        raise ValueError(f"Unknown Remove BG model: {mode}")
    path = model_file_path(mode)
    size = path.stat().st_size if path.is_file() else 0
    diag.model(
        f"UNINSTALL bg_remove:{mode.value}  path={path}  bytes={size}"
    )
    try:
        if path.is_file():
            path.unlink()
    except OSError as e:
        raise RuntimeError(f"Could not delete {path}: {e}") from e
    if path.exists():
        raise RuntimeError(f"Model file still exists after delete: {path}")
    diag.model(
        f"DELETED bg_remove:{mode.value}  path={path}  bytes={size}"
    )
    set_model_enabled(mode, False)
    ensure_selected_mode_valid()


def install_model(mode: BgRemoveMode) -> None:
    """Download ONNX weights via rembg (blocking; call from a worker thread)."""
    from backend.tools import diag
    from backend.tools.model_download_registry import (
        KIND_BG_REMOVE,
        DownloadCancelled,
        ModelDownloadRegistry,
        pooch_download_progress,
    )

    try:
        from rembg.sessions import sessions_class
    except ImportError as e:
        raise ImportError(
            'rembg is not installed. Run: pip install "rembg[cpu]"  (or re-run install.py)'
        ) from e

    reg = ModelDownloadRegistry.instance()
    if is_model_installed(mode):
        set_model_enabled(mode, True)
        reg.complete(KIND_BG_REMOVE, mode.value)
        return

    reg.begin(KIND_BG_REMOVE, mode.value)
    discard_partial(mode)
    target = mode.value
    try:
        reg.check_cancelled()
        for cls in sessions_class:
            try:
                name = cls.name()
            except Exception:
                continue
            if name == target:
                path = model_file_path(mode)
                diag.model(
                    f"DOWNLOAD bg_remove:{mode.value}  path={path}"
                )
                with pooch_download_progress():
                    cls.download_models()
                reg.check_cancelled()
                if not is_model_installed(mode):
                    discard_partial(mode)
                    reg.fail(KIND_BG_REMOVE, mode.value, keep_pending=False)
                    raise RuntimeError(
                        f"Download finished but model file missing: {model_file_path(mode)}"
                    )
                set_model_enabled(mode, True)
                reg.complete(KIND_BG_REMOVE, mode.value)
                diag.model(
                    f"INSTALLED bg_remove:{mode.value}  path={path}  "
                    f"bytes={path.stat().st_size}"
                )
                return
        reg.fail(KIND_BG_REMOVE, mode.value, keep_pending=False)
        raise ValueError(f"Unknown rembg model: {target}")
    except DownloadCancelled:
        discard_partial(mode)
        reg.fail(KIND_BG_REMOVE, mode.value, keep_pending=True)
        raise
    except Exception:
        if not is_model_installed(mode):
            discard_partial(mode)
            reg.fail(KIND_BG_REMOVE, mode.value, keep_pending=False)
        raise
