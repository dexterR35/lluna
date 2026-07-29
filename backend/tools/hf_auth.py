"""Hugging Face Hub auth for model downloads (Generate / Select Object)."""

from __future__ import annotations

import os
import logging
import shutil
from pathlib import Path
from typing import Optional

from backend.core.atomic import atomic_write_text

_ENV_KEYS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
logger = logging.getLogger(__name__)


def token_file_path() -> Path:
    """Local secret file (gitignored) — never commit this."""
    from backend.core.paths import AppPaths

    return AppPaths.resolve().config_dir / "hf_token"


def resolve_hf_token() -> Optional[str]:
    for key in _ENV_KEYS:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    path = token_file_path()
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError:
        pass
    return None


def apply_hf_token_to_env() -> Optional[str]:
    """Export token into the process env so huggingface_hub / transformers pick it up."""
    token = resolve_hf_token()
    if not token:
        return None
    os.environ["HF_TOKEN"] = token
    os.environ["HUGGING_FACE_HUB_TOKEN"] = token
    return token


def save_hf_token(token: str) -> Path:
    """Persist a read token locally and apply to env."""
    text = (token or "").strip()
    if not text:
        raise ValueError("HF token is empty.")
    path = token_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, text + "\n")
    try:
        path.chmod(0o600)
    except OSError as exc:
        logger.warning("Could not restrict token-file permissions: %s", type(exc).__name__)
    apply_hf_token_to_env()
    return path


def clear_hf_token() -> None:
    path = token_file_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        logger.warning("Could not remove token file: %s", type(exc).__name__)
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def has_hf_token() -> bool:
    return bool(resolve_hf_token())


def hf_download_cache_dir() -> Path:
    """Private, disposable Hub cache used only while Midgard downloads models."""
    from backend.core.paths import AppPaths

    return (
        AppPaths.resolve().models_dir
        / ".download_cache"
        / "huggingface"
        / "hub"
    )


def _shared_hf_hub_cache_dir() -> Path:
    """Resolve the Hub cache used by older Midgard releases."""
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        default = Path(hf_home).expanduser() / "hub"
    else:
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        cache_home = (
            Path(xdg_cache).expanduser()
            if xdg_cache
            else Path.home() / ".cache"
        )
        default = cache_home / "huggingface" / "hub"
    legacy = os.environ.get("HUGGINGFACE_HUB_CACHE")
    current = os.environ.get("HF_HUB_CACHE")
    return Path(current or legacy).expanduser() if current or legacy else default


def _repo_cache_folder(repo_id: str) -> str:
    parts = repo_id.split("/")
    if (
        len(parts) != 2
        or any(not part or part in {".", ".."} for part in parts)
        or any("\\" in part or "--" in part for part in parts)
    ):
        raise ValueError(f"Invalid Hugging Face model repository: {repo_id!r}")
    return "models--" + "--".join(parts)


def remove_hf_repo_cache(repo_id: str, *, include_shared: bool = True) -> None:
    """Remove cached download blobs for one model repository.

    Current downloads use Midgard's private cache. ``include_shared`` also
    removes the legacy global-cache copy left by older app versions.
    """
    folder = _repo_cache_folder(repo_id)
    roots = [hf_download_cache_dir()]
    if include_shared:
        roots.append(_shared_hf_hub_cache_dir())

    errors: list[str] = []
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        for target in (root / folder, root / ".locks" / folder):
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
            except OSError as exc:
                errors.append(f"{target}: {exc}")

    if errors:
        raise RuntimeError(
            "Could not delete cached model files: " + "; ".join(errors)
        )


def snapshot_download_kwargs() -> dict:
    """Extra kwargs for huggingface_hub.snapshot_download."""
    token = apply_hf_token_to_env()
    kwargs = {"cache_dir": str(hf_download_cache_dir())}
    if token:
        kwargs["token"] = token
    return kwargs


def snapshot_download_with_progress(
    *,
    repo_id: str,
    local_dir: str,
    allow_patterns: list[str],
) -> str:
    """Download an HF snapshot and report aggregate byte progress to the queue."""
    from huggingface_hub import snapshot_download

    from backend.tools.model_download_registry import (
        huggingface_download_total,
        huggingface_progress_tqdm,
    )

    kwargs = snapshot_download_kwargs()
    files = snapshot_download(
        repo_id=repo_id,
        local_dir=local_dir,
        allow_patterns=allow_patterns,
        dry_run=True,
        **kwargs,
    )
    total_bytes = sum(int(item.file_size) for item in files)
    with huggingface_download_total(total_bytes):
        return snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            allow_patterns=allow_patterns,
            tqdm_class=huggingface_progress_tqdm(),
            **kwargs,
        )
