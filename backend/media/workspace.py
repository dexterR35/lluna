"""Private per-job temporary workspace with explicit retention."""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class JobWorkspace:
    path: Path
    retain_on_failure: bool = False
    _closed: bool = False

    @classmethod
    def create(cls, prefix: str = "job") -> "JobWorkspace":
        path = Path(tempfile.mkdtemp(prefix=f"midgard-{prefix}-"))
        try:
            path.chmod(0o700)
        except OSError:
            pass
        return cls(path)

    def new_path(self, name: str, suffix: str = "") -> Path:
        safe = Path(name).name
        if not safe or safe in {".", ".."}:
            raise ValueError("workspace filename is invalid")
        return self.path / f"{safe}{suffix}"

    def close(self, *, failed: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        if failed and self.retain_on_failure:
            return
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> "JobWorkspace":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close(failed=exc is not None)


def cleanup_stale_workspaces(
    *,
    root: str | Path | None = None,
    older_than_seconds: float = 24 * 60 * 60,
) -> tuple[Path, ...]:
    """Remove only Midgard-owned workspace directories older than the limit."""
    base = Path(root) if root is not None else Path(tempfile.gettempdir())
    cutoff = time.time() - max(0.0, older_than_seconds)
    removed: list[Path] = []
    for path in base.glob("midgard-*-*"):
        try:
            if path.is_dir() and not path.is_symlink() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path)
                removed.append(path)
        except OSError:
            continue
    return tuple(removed)
