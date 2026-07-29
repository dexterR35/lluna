from __future__ import annotations

import threading
import time

import pytest

from backend.tools.model_download_queue import ModelDownloadQueue


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for model queue state")


def test_queue_exposes_progress_positions_and_session_history() -> None:
    queue = ModelDownloadQueue()
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    release_second = threading.Event()

    def first_work() -> None:
        first_started.set()
        assert release_first.wait(timeout=2)

    def second_work() -> None:
        second_started.set()
        assert release_second.wait(timeout=2)

    queue.enqueue("generate", "flux", first_work, lambda _err: None)
    queue.enqueue("enhance", "x2", second_work, lambda _err: None)
    assert first_started.wait(timeout=2)

    queue.report_current_progress(42, detail="42 / 100 bytes")
    jobs = queue.jobs()
    assert [(job.key, job.state, job.position) for job in jobs] == [
        ("flux", "active", 0),
        ("x2", "queued", 1),
    ]
    assert jobs[0].progress == 42

    release_first.set()
    assert second_started.wait(timeout=2)
    jobs = queue.jobs()
    assert jobs[0].key == "x2"
    assert jobs[0].state == "active"
    assert any(job.key == "flux" and job.state == "completed" for job in jobs)

    release_second.set()
    _wait_until(lambda: not queue.is_busy())
    history = queue.jobs()
    assert [job.key for job in history[:2]] == ["x2", "flux"]
    assert all(job.state == "completed" for job in history[:2])

    queue.clear_finished()
    assert queue.jobs() == []


def test_queue_tracks_uninstall_operation_and_failure() -> None:
    queue = ModelDownloadQueue()

    def fail() -> None:
        raise RuntimeError("network failed")

    queue.enqueue(
        "generate",
        "flux",
        fail,
        lambda _err: None,
        operation="uninstall",
    )
    _wait_until(lambda: not queue.is_busy())

    job = queue.jobs()[0]
    assert job.operation == "uninstall"
    assert job.state == "failed"
    assert job.error == "network failed"


def test_direct_download_reporthook_updates_active_percentage(monkeypatch) -> None:
    from backend.tools.model_download_registry import urllib_cancel_reporthook

    queue = ModelDownloadQueue()
    monkeypatch.setattr(ModelDownloadQueue, "_instance", queue)
    reported = threading.Event()
    release = threading.Event()

    def work() -> None:
        urllib_cancel_reporthook(5, 10, 100)
        reported.set()
        assert release.wait(timeout=2)

    queue.enqueue("enhance", "x2", work, lambda _err: None)
    assert reported.wait(timeout=2)
    assert queue.jobs(include_finished=False)[0].progress == 47
    release.set()
    _wait_until(lambda: not queue.is_busy())


def test_huggingface_byte_adapter_updates_active_percentage(monkeypatch) -> None:
    pytest.importorskip("tqdm")
    from backend.tools.model_download_registry import (
        huggingface_download_total,
        huggingface_progress_tqdm,
    )

    queue = ModelDownloadQueue()
    monkeypatch.setattr(ModelDownloadQueue, "_instance", queue)
    reported = threading.Event()
    release = threading.Event()

    def work() -> None:
        bar_class = huggingface_progress_tqdm()
        with huggingface_download_total(100):
            bar = bar_class(
                total=100,
                desc="Reconstructing (incomplete total...)",
                unit="B",
            )
            bar.update(40)
            reported.set()
            assert release.wait(timeout=2)
            bar.close()

    queue.enqueue("generate", "flux", work, lambda _err: None)
    assert reported.wait(timeout=2)
    assert queue.jobs(include_finished=False)[0].progress == 38
    release.set()
    _wait_until(lambda: not queue.is_busy())
