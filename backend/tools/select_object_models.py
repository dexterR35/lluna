"""Select Object model catalog (SAM2 + Grounding DINO): install paths and pair resolver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from enum import Enum, unique

from backend.tools.constant import SelectObjectModelId

_MARKER = ".midgard_installed"


@unique
class SelectObjectPairId(str, Enum):
    """Matched SAM2 + DINO weights (always installed and used together)."""

    FAST = "fast"  # SAM2 tiny + DINO tiny
    COMPLEX = "complex"  # SAM2 large + DINO base


@dataclass(frozen=True)
class SelectObjectPairInfo:
    pair_id: SelectObjectPairId
    desc_key: str
    is_default: bool = False


@dataclass(frozen=True)
class SelectObjectModelInfo:
    model_id: SelectObjectModelId
    hf_repo: str
    desc_key: str
    is_default: bool = False
    is_optional: bool = False


MODEL_CATALOG: List[SelectObjectModelInfo] = [
    SelectObjectModelInfo(
        SelectObjectModelId.SAM2_TINY,
        hf_repo="facebook/sam2-hiera-tiny",
        desc_key="SAM2_TINY",
        is_default=True,
    ),
    SelectObjectModelInfo(
        SelectObjectModelId.SAM2_LARGE,
        hf_repo="facebook/sam2-hiera-large",
        desc_key="SAM2_LARGE",
        is_optional=True,
    ),
    SelectObjectModelInfo(
        SelectObjectModelId.DINO_TINY,
        hf_repo="IDEA-Research/grounding-dino-tiny",
        desc_key="DINO_TINY",
        is_default=True,
    ),
    SelectObjectModelInfo(
        SelectObjectModelId.DINO_BASE,
        hf_repo="IDEA-Research/grounding-dino-base",
        desc_key="DINO_BASE",
        is_optional=True,
    ),
]

_CATALOG: Dict[SelectObjectModelId, SelectObjectModelInfo] = {
    m.model_id: m for m in MODEL_CATALOG
}

DEFAULT_PREFETCH = (
    SelectObjectModelId.SAM2_TINY,
    SelectObjectModelId.DINO_TINY,
)

PAIR_MEMBERS: Dict[SelectObjectPairId, Tuple[SelectObjectModelId, SelectObjectModelId]] = {
    SelectObjectPairId.FAST: (
        SelectObjectModelId.SAM2_TINY,
        SelectObjectModelId.DINO_TINY,
    ),
    SelectObjectPairId.COMPLEX: (
        SelectObjectModelId.SAM2_LARGE,
        SelectObjectModelId.DINO_BASE,
    ),
}

PAIR_CATALOG: List[SelectObjectPairInfo] = [
    SelectObjectPairInfo(SelectObjectPairId.FAST, "PAIR_FAST", is_default=True),
    SelectObjectPairInfo(SelectObjectPairId.COMPLEX, "PAIR_COMPLEX"),
]


def models_root() -> Path:
    from backend.config import BASE_DIR

    root = Path(BASE_DIR) / "models" / "select_object"
    root.mkdir(parents=True, exist_ok=True)
    return root


def model_dir(model_id: SelectObjectModelId) -> Path:
    return models_root() / model_id.value


def catalog_info(model_id: SelectObjectModelId) -> Optional[SelectObjectModelInfo]:
    return _CATALOG.get(model_id)


def is_model_installed(model_id: SelectObjectModelId) -> bool:
    path = model_dir(model_id)
    marker = path / _MARKER
    if marker.is_file():
        return True
    # HF snapshot leaves config.json at repo root
    if (path / "config.json").is_file():
        return True
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def is_fast_pair_installed() -> bool:
    return is_pair_installed(SelectObjectPairId.FAST)


def is_complex_pair_installed() -> bool:
    return is_pair_installed(SelectObjectPairId.COMPLEX)


def is_pair_installed(pair_id: SelectObjectPairId) -> bool:
    sam2_id, dino_id = PAIR_MEMBERS[pair_id]
    return is_model_installed(sam2_id) and is_model_installed(dino_id)


def pair_install_state(pair_id: SelectObjectPairId) -> str:
    """``installed`` | ``partial`` | ``missing``."""
    sam2_id, dino_id = PAIR_MEMBERS[pair_id]
    a = is_model_installed(sam2_id)
    b = is_model_installed(dino_id)
    if a and b:
        return "installed"
    if a or b:
        return "partial"
    return "missing"


def is_active_pair_ready(more_complex: bool | None = None) -> bool:
    sam2_id, dino_id = resolve_pair(more_complex)
    return is_model_installed(sam2_id) and is_model_installed(dino_id)


def resolve_pair(more_complex: bool | None = None) -> Tuple[SelectObjectModelId, SelectObjectModelId]:
    """More complex ON + both optional weights → large+base; else tiny+tiny."""
    if more_complex is None:
        from backend.config import config

        more_complex = bool(config.selectObjectMoreComplex.value)
    if more_complex and is_complex_pair_installed():
        return SelectObjectModelId.SAM2_LARGE, SelectObjectModelId.DINO_BASE
    return SelectObjectModelId.SAM2_TINY, SelectObjectModelId.DINO_TINY


def ensure_defaults_installed() -> None:
    """Install fast pair if missing (blocking). Skips models already on disk."""
    install_pair(SelectObjectPairId.FAST, skip_if_complete=True)


def install_pair(pair_id: SelectObjectPairId, *, skip_if_complete: bool = False) -> None:
    """Install SAM2 + DINO for one pair only; never downloads the other pair."""
    if skip_if_complete and is_pair_installed(pair_id):
        return
    try:
        members = PAIR_MEMBERS[pair_id]
    except KeyError as e:
        raise ValueError(f"Unknown Select Object pair: {pair_id}") from e
    for mid in members:
        install_model(mid)


def ensure_active_pair_installed(more_complex: bool | None = None) -> None:
    """Install only the pair Select Object will use; never both pairs at once."""
    if more_complex is None:
        from backend.config import config

        more_complex = bool(config.selectObjectMoreComplex.value)
    if more_complex:
        if is_complex_pair_installed():
            return
        install_pair(SelectObjectPairId.COMPLEX, skip_if_complete=True)
        return
    install_pair(SelectObjectPairId.FAST, skip_if_complete=True)


def prefetch_on_install() -> None:
    """First-install / re-install: download only missing default (tiny) weights."""
    ensure_defaults_installed()


def install_model(model_id: SelectObjectModelId) -> Path:
    """Download HF weights into backend/models/select_object/<id>/."""
    info = catalog_info(model_id)
    if info is None:
        raise ValueError(f"Unknown Select Object model: {model_id}")

    dest = model_dir(model_id)
    if is_model_installed(model_id):
        return dest

    dest.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        raise RuntimeError(
            "huggingface_hub is required for Select Object models. "
            "Re-run install.py or pip install huggingface_hub."
        ) from e

    snapshot_download(
        repo_id=info.hf_repo,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
    )
    (dest / _MARKER).touch()

    if not is_model_installed(model_id):
        raise RuntimeError(f"Download finished but model missing: {dest}")
    return dest


def local_repo_path(model_id: SelectObjectModelId) -> Path:
    path = model_dir(model_id)
    if not is_model_installed(model_id):
        raise FileNotFoundError(f"Select Object model not installed: {model_id.value}")
    return path
