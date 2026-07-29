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


def test_download_panel_shows_active_percent_and_queued_model(
    qtbot,
    monkeypatch,
) -> None:
    from backend.tools.model_download_queue import ModelDownloadQueue
    from ui.component import model_download_panel as panel_module

    queue = ModelDownloadQueue()
    monkeypatch.setattr(panel_module, "model_download_queue", lambda: queue)
    panel = panel_module.ModelDownloadPanel()
    qtbot.addWidget(panel)

    started = threading.Event()
    release = threading.Event()

    def work() -> None:
        started.set()
        assert release.wait(timeout=2)

    queue.enqueue("generate", "flux", work, lambda _err: None)
    queue.enqueue("enhance", "x2", lambda: None, lambda _err: None)
    qtbot.waitUntil(started.is_set, timeout=2000)
    queue.report_current_progress(37)
    panel.refresh()

    rows = [
        panel.rows_layout.itemAt(index).widget()
        for index in range(panel.rows_layout.count())
        if panel.rows_layout.itemAt(index).widget() is not None
    ]
    assert len(rows) == 2
    assert rows[0].progress_bar.maximum() == 100
    assert not rows[0].stop_button.isHidden()
    assert rows[1].metrics_label.text() == "Queue position 1"
    assert rows[0].status_label.text() == "Installing · 37%"
    assert rows[1].status_label.text() == "Queued · 1 ahead"

    release.set()
    qtbot.waitUntil(lambda: not queue.is_busy(), timeout=2000)
