"""Select Object model catalog (SAM2 + Grounding DINO): install paths and pair resolver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from enum import Enum, unique

from backend.tools.constant import SelectObjectModelId

_MARKER = ".midgard_installed"

_SAM2_ALLOW_PATTERNS = (
    "*.json",
    "model.safetensors",
)

_DINO_ALLOW_PATTERNS = (
    "*.json",
    "*.txt",
    "model.safetensors",
)


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
    download_allow_patterns: tuple[str, ...]
    is_default: bool = False
    is_optional: bool = False


MODEL_CATALOG: List[SelectObjectModelInfo] = [
    SelectObjectModelInfo(
        SelectObjectModelId.SAM2_TINY,
        hf_repo="facebook/sam2-hiera-tiny",
        desc_key="SAM2_TINY",
        download_allow_patterns=_SAM2_ALLOW_PATTERNS,
        is_default=True,
    ),
    SelectObjectModelInfo(
        SelectObjectModelId.SAM2_LARGE,
        hf_repo="facebook/sam2-hiera-large",
        desc_key="SAM2_LARGE",
        download_allow_patterns=_SAM2_ALLOW_PATTERNS,
        is_optional=True,
    ),
    SelectObjectModelInfo(
        SelectObjectModelId.DINO_TINY,
        hf_repo="IDEA-Research/grounding-dino-tiny",
        desc_key="DINO_TINY",
        download_allow_patterns=_DINO_ALLOW_PATTERNS,
        is_default=True,
    ),
    SelectObjectModelInfo(
        SelectObjectModelId.DINO_BASE,
        hf_repo="IDEA-Research/grounding-dino-base",
        desc_key="DINO_BASE",
        download_allow_patterns=_DINO_ALLOW_PATTERNS,
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
    from backend.core.paths import PATHS

    root = PATHS.models_dir / "select_object"
    root.mkdir(parents=True, exist_ok=True)
    return root


def model_dir(model_id: SelectObjectModelId) -> Path:
    return models_root() / model_id.value


def catalog_info(model_id: SelectObjectModelId) -> Optional[SelectObjectModelInfo]:
    return _CATALOG.get(model_id)


def _validate_download_snapshot(info: SelectObjectModelInfo, dest: Path) -> None:
    required = ["config.json", "model.safetensors", "preprocessor_config.json"]
    if info.model_id in {
        SelectObjectModelId.SAM2_TINY,
        SelectObjectModelId.SAM2_LARGE,
    }:
        required.append("processor_config.json")
    else:
        required.extend(["tokenizer_config.json", "vocab.txt"])
    missing = [relative for relative in required if not (dest / relative).is_file()]
    if missing:
        raise RuntimeError(
            f"Downloaded {info.model_id.value} snapshot is incomplete; missing: "
            + ", ".join(missing)
        )


def is_model_installed(model_id: SelectObjectModelId) -> bool:
    path = model_dir(model_id)
    marker = path / _MARKER
    if marker.is_file():
        return True
    if not (path / "config.json").is_file():
        return False
    # Don't adopt mid-download dirs while a pair install is pending
    try:
        from backend.tools.model_download_registry import (
            KIND_SELECT_OBJECT,
            ModelDownloadRegistry,
        )

        pending_pairs = {
            p.key
            for p in ModelDownloadRegistry.instance().list_pending()
            if p.kind == KIND_SELECT_OBJECT
        }
        for pair_id, members in PAIR_MEMBERS.items():
            if pair_id.value in pending_pairs and model_id in members:
                return False
    except Exception:
        pass
    try:
        marker.touch()
    except OSError:
        pass
    return True


def discard_partial(model_id: SelectObjectModelId) -> None:
    """Remove incomplete HF snapshot so the next install starts over."""
    import shutil

    dest = model_dir(model_id)
    marker = dest / _MARKER
    if marker.is_file():
        return
    try:
        if dest.is_dir():
            shutil.rmtree(dest)
    except OSError:
        pass


def discard_pair_partial(pair_id: SelectObjectPairId) -> None:
    """Wipe pair dirs so an interrupted pair install starts over from scratch."""
    import shutil

    for mid in PAIR_MEMBERS[pair_id]:
        dest = model_dir(mid)
        try:
            if dest.is_dir():
                shutil.rmtree(dest)
        except OSError:
            pass


def uninstall_model(model_id: SelectObjectModelId) -> None:
    """Delete one local HF snapshot (even if marked installed)."""
    import shutil

    info = catalog_info(model_id)
    if info is None:
        raise ValueError(f"Unknown Select Object model: {model_id}")
    from backend.tools.hf_auth import remove_hf_repo_cache

    # Older releases kept a second copy in the shared Hugging Face cache.
    remove_hf_repo_cache(info.hf_repo)
    dest = model_dir(model_id)
    try:
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()
    except OSError as e:
        raise RuntimeError(f"Could not delete {dest}: {e}") from e


def uninstall_pair(pair_id: SelectObjectPairId) -> None:
    """Delete both members of a pair so it can be reinstalled later."""
    try:
        members = PAIR_MEMBERS[pair_id]
    except KeyError as e:
        raise ValueError(f"Unknown Select Object pair: {pair_id}") from e
    for mid in members:
        uninstall_model(mid)
    if pair_id == SelectObjectPairId.COMPLEX:
        from backend.configuration.service import get_settings, update_settings

        if get_settings().object_selection.more_complex:
            update_settings({"object_selection": {"more_complex": False}})


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
        from backend.configuration.service import get_settings

        more_complex = bool(get_settings().object_selection.more_complex)
    if more_complex and is_complex_pair_installed():
        return SelectObjectModelId.SAM2_LARGE, SelectObjectModelId.DINO_BASE
    return SelectObjectModelId.SAM2_TINY, SelectObjectModelId.DINO_TINY


def ensure_defaults_installed() -> None:
    """Install fast pair if missing (blocking). Skips models already on disk."""
    install_pair(SelectObjectPairId.FAST, skip_if_complete=True)


def install_pair(pair_id: SelectObjectPairId, *, skip_if_complete: bool = False) -> None:
    """Install SAM2 + DINO for one pair only; never downloads the other pair."""
    from backend.tools.model_download_registry import (
        KIND_SELECT_OBJECT,
        DownloadCancelled,
        ModelDownloadRegistry,
        download_progress_range,
    )

    if skip_if_complete and is_pair_installed(pair_id):
        ModelDownloadRegistry.instance().complete(KIND_SELECT_OBJECT, pair_id.value)
        return
    try:
        members = PAIR_MEMBERS[pair_id]
    except KeyError as e:
        raise ValueError(f"Unknown Select Object pair: {pair_id}") from e

    reg = ModelDownloadRegistry.instance()
    reg.begin(KIND_SELECT_OBJECT, pair_id.value)
    try:
        missing = [mid for mid in members if not is_model_installed(mid)]
        count = max(len(missing), 1)
        for index, mid in enumerate(missing):
            reg.check_cancelled()
            start = int(index * 95 / count)
            end = int((index + 1) * 95 / count)
            with download_progress_range(start, end):
                install_model(mid)
        reg.check_cancelled()
        if not is_pair_installed(pair_id):
            discard_pair_partial(pair_id)
            reg.fail(KIND_SELECT_OBJECT, pair_id.value, keep_pending=False)
            raise RuntimeError(f"Pair install incomplete: {pair_id.value}")
        reg.complete(KIND_SELECT_OBJECT, pair_id.value)
    except DownloadCancelled:
        discard_pair_partial(pair_id)
        reg.fail(KIND_SELECT_OBJECT, pair_id.value, keep_pending=True)
        raise
    except Exception:
        if not is_pair_installed(pair_id):
            discard_pair_partial(pair_id)
            reg.fail(KIND_SELECT_OBJECT, pair_id.value, keep_pending=False)
        raise


def ensure_active_pair_installed(more_complex: bool | None = None) -> None:
    """Install only the pair Select Object will use; never both pairs at once."""
    if more_complex is None:
        from backend.configuration.service import get_settings

        more_complex = bool(get_settings().object_selection.more_complex)
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
    from backend.tools.model_download_registry import (
        DownloadCancelled,
        ModelDownloadRegistry,
    )

    info = catalog_info(model_id)
    if info is None:
        raise ValueError(f"Unknown Select Object model: {model_id}")

    dest = model_dir(model_id)
    if is_model_installed(model_id):
        return dest

    discard_partial(model_id)
    dest.mkdir(parents=True, exist_ok=True)
    reg = ModelDownloadRegistry.instance()

    try:
        import huggingface_hub  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "huggingface_hub is required for Select Object models. "
            "Re-run install.py or pip install huggingface_hub."
        ) from e

    from backend.tools.hf_auth import (
        apply_hf_token_to_env,
        remove_hf_repo_cache,
        snapshot_download_with_progress,
    )

    apply_hf_token_to_env()
    try:
        reg.check_cancelled()
        snapshot_download_with_progress(
            repo_id=info.hf_repo,
            local_dir=str(dest),
            allow_patterns=list(info.download_allow_patterns),
        )
        reg.check_cancelled()
        _validate_download_snapshot(info, dest)
        # Keep the runtime snapshot, not a second copy of the same weights.
        remove_hf_repo_cache(info.hf_repo, include_shared=False)
    except DownloadCancelled:
        discard_partial(model_id)
        try:
            remove_hf_repo_cache(info.hf_repo, include_shared=False)
        except Exception:
            pass
        raise
    except Exception:
        discard_partial(model_id)
        try:
            remove_hf_repo_cache(info.hf_repo, include_shared=False)
        except Exception:
            pass
        raise
    (dest / _MARKER).touch()

    if not is_model_installed(model_id):
        discard_partial(model_id)
        raise RuntimeError(f"Download finished but model missing: {dest}")
    return dest


def local_repo_path(model_id: SelectObjectModelId) -> Path:
    path = model_dir(model_id)
    if not is_model_installed(model_id):
        raise FileNotFoundError(f"Select Object model not installed: {model_id.value}")
    return path
