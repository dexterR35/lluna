"""Recovery helpers shared by typed and legacy configuration loaders."""

from __future__ import annotations

import json
import time
from pathlib import Path


def backup_if_corrupt_json(path: str | Path) -> Path | None:
    """Move a malformed JSON file aside and return the backup path."""
    source = Path(path)
    if not source.is_file():
        return None
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("top-level value must be an object")
        return None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        backup = source.with_name(
            f"{source.name}.corrupt-{int(time.time())}"
        )
        try:
            source.replace(backup)
        except OSError:
            return None
        return backup
