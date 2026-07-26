"""Hugging Face Hub auth for model downloads (Generate / Select Object)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_ENV_KEYS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")


def token_file_path() -> Path:
    """Local secret file (gitignored) — never commit this."""
    from backend.config import BASE_DIR

    # Project root config/ next to config.json
    root = Path(BASE_DIR).resolve().parent
    return root / "config" / "hf_token"


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
    path.write_text(text + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    apply_hf_token_to_env()
    return path


def clear_hf_token() -> None:
    path = token_file_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def has_hf_token() -> bool:
    return bool(resolve_hf_token())


def snapshot_download_kwargs() -> dict:
    """Extra kwargs for huggingface_hub.snapshot_download."""
    token = apply_hf_token_to_env()
    return {"token": token} if token else {}
