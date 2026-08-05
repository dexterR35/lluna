from __future__ import annotations

import os
import time
from pathlib import Path

from backend.media.workspace import cleanup_stale_workspaces


def test_cleanup_removes_only_stale_lluna_directories(tmp_path: Path) -> None:
    stale = tmp_path / "lluna-test-old"
    fresh = tmp_path / "lluna-test-new"
    unrelated = tmp_path / "other-old"
    for path in (stale, fresh, unrelated):
        path.mkdir()
    old = time.time() - 100
    os.utime(stale, (old, old))
    os.utime(unrelated, (old, old))
    removed = cleanup_stale_workspaces(root=tmp_path, older_than_seconds=50)
    assert stale in removed
    assert not stale.exists()
    assert fresh.exists()
    assert unrelated.exists()
