from __future__ import annotations

import threading

import pytest

pytestmark = pytest.mark.gui

pytest.importorskip("PySide6")


def test_model_job_completion_returns_to_qt_thread_and_unlocks_queue(
    qtbot,
    monkeypatch,
) -> None:
    from backend.tools.model_download_queue import ModelDownloadQueue
    from ui.component.cards import model_install_helpers as helpers

    queue = ModelDownloadQueue()
    monkeypatch.setattr(helpers, "model_download_queue", lambda: queue)

    started = threading.Event()
    release = threading.Event()
    completed: list[BaseException | None] = []
    notifications: list[str | None] = []

    def work() -> None:
        started.set()
        assert release.wait(timeout=2)

    def listener() -> None:
        notifications.append(queue.job_state("test", "model"))

    helpers.register_queue_listener(listener)
    try:
        helpers.enqueue_model_job(
            "test",
            "model",
            work,
            lambda err: completed.append(err),
        )
        qtbot.waitUntil(started.is_set, timeout=2000)
        release.set()
        qtbot.waitUntil(lambda: bool(completed), timeout=2000)
        qtbot.waitUntil(lambda: not queue.is_busy(), timeout=2000)

        assert completed == [None]
        assert queue.job_state("test", "model") is None
        assert notifications
    finally:
        helpers.unregister_queue_listener(listener)
