"""Hugging Face Hub auth for model downloads (Generate / Select Object)."""

from __future__ import annotations

import os
import logging
import shutil
from pathlib import Path
from typing import Optional

from backend.core.atomic import atomic_write_text

_ENV_KEYS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
_KEYRING_SERVICE = "Lluna"
_KEYRING_USER = "huggingface-token"
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
    try:
        import keyring

        saved = (keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER) or "").strip()
        if saved:
            return saved
    except Exception:
        # Linux desktops without a Secret Service backend use the restricted
        # fallback file below. Authentication must still work offline.
        pass
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
    """Persist a token in the OS credential store, with a 0600 file fallback."""
    text = (token or "").strip()
    if not text:
        raise ValueError("HF token is empty.")
    path = token_file_path()
    def apply_saved() -> None:
        for key in _ENV_KEYS:
            os.environ[key] = text

    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, text)
        if path.is_file():
            path.unlink()
        apply_saved()
        return path
    except Exception as exc:
        logger.info("OS credential storage unavailable; using restricted token file: %s", type(exc).__name__)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, text + "\n")
    try:
        path.chmod(0o600)
    except OSError as exc:
        logger.warning("Could not restrict token-file permissions: %s", type(exc).__name__)
    apply_saved()
    return path


def clear_hf_token() -> None:
    path = token_file_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        logger.warning("Could not remove token file: %s", type(exc).__name__)
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
    except Exception:
        pass
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def has_hf_token() -> bool:
    return bool(resolve_hf_token())


def validate_hf_token(token: str | None = None) -> dict:
    """Validate a personal access token without returning or logging the secret."""
    from huggingface_hub import HfApi

    candidate = (token or resolve_hf_token() or "").strip()
    if not candidate:
        raise ValueError("Enter a Hugging Face access token.")
    identity = HfApi(token=candidate).whoami(token=candidate)
    name = str(identity.get("name") or identity.get("fullname") or "Connected user")
    auth = identity.get("auth") if isinstance(identity, dict) else None
    access = auth.get("accessToken", {}) if isinstance(auth, dict) else {}
    role = str(access.get("role") or "read") if isinstance(access, dict) else "read"
    return {"connected": True, "account": name, "role": role}


def hf_auth_status(*, verify: bool = False) -> dict:
    token = resolve_hf_token()
    if not token:
        return {"connected": False, "account": "", "role": "", "storage": "none"}
    storage = "restricted-file" if token_file_path().is_file() else "os-keychain-or-environment"
    if not verify:
        return {"connected": True, "account": "", "role": "", "storage": storage}
    return {**validate_hf_token(token), "storage": storage}


def hf_download_cache_dir() -> Path:
    """Private, disposable Hub cache used only while Lluna downloads models."""
    from backend.core.paths import AppPaths

    return (
        AppPaths.resolve().models_dir
        / ".download_cache"
        / "huggingface"
        / "hub"
    )


def _shared_hf_hub_cache_dir() -> Path:
    """Resolve the Hub cache used by older Lluna releases."""
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

    Current downloads use Lluna's private cache. ``include_shared`` also
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
    revision: str | None = None,
    ignore_patterns: list[str] | None = None,
) -> str:
    """Download an HF snapshot, report aggregate byte progress, and verify
    every downloaded file's size against what the Hub reported before the
    transfer started (catches truncated/corrupted transfers - installers
    previously only checked that expected *filenames* were present, not
    that their bytes actually arrived intact)."""
    from huggingface_hub import snapshot_download

    from backend.tools.shared.download_registry import (
        huggingface_download_total,
        huggingface_progress_tqdm,
    )

    kwargs = snapshot_download_kwargs()
    download_args = {
        "repo_id": repo_id,
        "local_dir": local_dir,
        "allow_patterns": allow_patterns,
        **({"revision": revision} if revision else {}),
        **({"ignore_patterns": ignore_patterns} if ignore_patterns else {}),
    }
    files = snapshot_download(
        **download_args,
        dry_run=True,
        **kwargs,
    )
    total_bytes = sum(int(item.file_size) for item in files)
    expected_sizes = {item.filename: int(item.file_size) for item in files}
    from backend.tools.shared.disk_preflight import ensure_disk_space

    ensure_disk_space(total_bytes, context=repo_id)
    with huggingface_download_total(total_bytes):
        result = snapshot_download(
            **download_args,
            tqdm_class=huggingface_progress_tqdm(),
            **kwargs,
        )
    _verify_snapshot_sizes(Path(local_dir), expected_sizes)
    return result


def _verify_snapshot_sizes(local_dir: Path, expected_sizes: dict[str, int]) -> None:
    problems: list[str] = []
    for filename, expected_size in expected_sizes.items():
        path = local_dir / filename
        actual_size = path.stat().st_size if path.is_file() else None
        if actual_size != expected_size:
            state = "missing" if actual_size is None else f"{actual_size} of {expected_size} bytes"
            problems.append(f"{filename} ({state})")
    if problems:
        raise RuntimeError(
            "Downloaded snapshot has missing or truncated files: " + ", ".join(problems[:12])
        )


def require_snapshot_files(
    dest: Path,
    required_files: list[str],
    *,
    name: str,
    required_glob_dirs: dict[str, str] | None = None,
) -> None:
    """Raise if a curated list of required files/globs isn't present after a
    snapshot download - distinct from `_verify_snapshot_sizes`'s "everything
    the Hub said it sent arrived intact" check: this asserts the specific
    files *this adapter* actually needs to load are among them."""
    missing = [rel for rel in required_files if not (dest / rel).is_file()]
    for rel, pattern in (required_glob_dirs or {}).items():
        if not any((dest / rel).glob(pattern)):
            missing.append(f"{rel}/{pattern}")
    if missing:
        raise RuntimeError(
            f"Downloaded {name} snapshot is incomplete; missing: " + ", ".join(missing[:12])
        )
