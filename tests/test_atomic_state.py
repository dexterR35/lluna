from __future__ import annotations

import json
import threading
from pathlib import Path

from backend.core.atomic import atomic_write_json
from backend.tools.shared.download_queue import ModelDownloadQueue


def test_atomic_json_replaces_complete_document(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    atomic_write_json(path, {"value": 1})
    atomic_write_json(path, {"value": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 2}
    assert not list(tmp_path.glob("*.tmp"))


def test_download_queue_listener_can_query_without_deadlock() -> None:
    queue = ModelDownloadQueue()
    observed: list[int] = []
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def work() -> None:
        started.set()
        assert release.wait(timeout=2)

    queue.add_listener(lambda: observed.append(queue.pending_count()))
    queue.enqueue("test", "one", work, lambda error: finished.set())
    assert started.wait(timeout=2)
    release.set()
    assert finished.wait(timeout=2)
    assert observed
