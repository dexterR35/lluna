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


def test_queue_exposes_bytes_speed_elapsed_and_eta() -> None:
    queue = ModelDownloadQueue()
    reported = threading.Event()
    release = threading.Event()

    def work() -> None:
        queue.report_current_progress(
            10,
            downloaded_bytes=100,
            total_bytes=1000,
        )
        time.sleep(0.02)
        queue.report_current_progress(
            40,
            downloaded_bytes=400,
            total_bytes=1000,
        )
        reported.set()
        assert release.wait(timeout=2)

    queue.enqueue("generate", "flux", work, lambda _err: None)
    assert reported.wait(timeout=2)

    job = queue.jobs(include_finished=False)[0]
    assert job.downloaded_bytes == 400
    assert job.total_bytes == 1000
    assert job.bytes_per_second is not None
    assert job.bytes_per_second > 0
    assert job.elapsed_seconds > 0
    assert job.eta_seconds is not None
    assert job.eta_seconds > 0

    release.set()
    _wait_until(lambda: not queue.is_busy())


def test_stopping_current_job_continues_with_next_queued_job(
    monkeypatch,
    tmp_path,
) -> None:
    from backend.tools.model_download_registry import (
        DownloadCancelled,
        ModelDownloadRegistry,
    )

    monkeypatch.setenv("LLUNA_CONFIG_DIR", str(tmp_path))
    registry = ModelDownloadRegistry()
    monkeypatch.setattr(ModelDownloadRegistry, "_instance", registry)

    queue = ModelDownloadQueue()
    first_started = threading.Event()
    second_started = threading.Event()
    completed: list[tuple[str, BaseException | None]] = []

    def first_work() -> None:
        first_started.set()
        while True:
            registry.check_cancelled()
            time.sleep(0.01)

    first_position = queue.enqueue(
        "generate",
        "flux",
        first_work,
        lambda err: completed.append(("flux", err)),
    )
    assert first_position == 0
    queue.enqueue(
        "enhance",
        "x2",
        second_started.set,
        lambda err: completed.append(("x2", err)),
    )
    assert first_started.wait(timeout=2)

    active_id = queue.jobs(include_finished=False)[0].job_id
    assert queue.stop_job(active_id)
    stopping = next(job for job in queue.jobs() if job.key == "flux")
    assert stopping.state == "stopping"
    assert stopping.detail == "Cancelling and rolling back installation…"
    assert second_started.wait(timeout=2)
    _wait_until(lambda: not queue.is_busy())
    _wait_until(lambda: any(key == "flux" for key, _err in completed))

    stopped = next(job for job in queue.jobs() if job.key == "flux")
    finished = next(job for job in queue.jobs() if job.key == "x2")
    assert stopped.state == "cancelled"
    assert finished.state == "completed"
    assert isinstance(dict(completed)["flux"], DownloadCancelled)


def test_stopping_queued_job_removes_only_that_item(monkeypatch, tmp_path) -> None:
    from backend.tools.model_download_registry import (
        DownloadCancelled,
        ModelDownloadRegistry,
    )

    monkeypatch.setenv("LLUNA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        ModelDownloadRegistry,
        "_instance",
        ModelDownloadRegistry(),
    )

    queue = ModelDownloadQueue()
    first_started = threading.Event()
    release_first = threading.Event()
    third_started = threading.Event()
    completed: list[tuple[str, BaseException | None]] = []

    def first_work() -> None:
        first_started.set()
        assert release_first.wait(timeout=2)

    queue.enqueue("test", "one", first_work, lambda _err: None)
    queue.enqueue(
        "test",
        "two",
        lambda: None,
        lambda err: completed.append(("two", err)),
    )
    queue.enqueue("test", "three", third_started.set, lambda _err: None)
    assert first_started.wait(timeout=2)

    queued = next(job for job in queue.jobs() if job.key == "two")
    assert queue.stop_job(queued.job_id)
    release_first.set()
    assert third_started.wait(timeout=2)
    _wait_until(lambda: not queue.is_busy())

    stopped = next(job for job in queue.jobs() if job.key == "two")
    assert stopped.state == "cancelled"
    assert isinstance(dict(completed)["two"], DownloadCancelled)


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
                total=0,
                desc="Downloading (incomplete total...)",
                unit="B",
                name="huggingface_hub.snapshot_download",
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


def test_pooch_byte_adapter_updates_active_metrics(monkeypatch) -> None:
    pytest.importorskip("tqdm")
    from backend.tools.model_download_registry import pooch_progress_tqdm

    queue = ModelDownloadQueue()
    monkeypatch.setattr(ModelDownloadQueue, "_instance", queue)
    reported = threading.Event()
    release = threading.Event()

    def work() -> None:
        bar = pooch_progress_tqdm()(total=100, unit="B")
        bar.update(40)
        reported.set()
        assert release.wait(timeout=2)
        bar.close()

    queue.enqueue("enhance", "RealESRGAN_x2plus", work, lambda _err: None)
    assert reported.wait(timeout=2)
    job = queue.jobs(include_finished=False)[0]
    assert job.progress == 38
    assert job.downloaded_bytes == 40
    assert job.total_bytes == 100
    release.set()
    _wait_until(lambda: not queue.is_busy())


def test_model_service_serializes_multiple_installs_in_fifo_order(monkeypatch) -> None:
    from backend.models import service

    queue = ModelDownloadQueue()
    monkeypatch.setattr(ModelDownloadQueue, "_instance", queue)
    monkeypatch.setattr(service, "_QUEUE_EVENT_SOURCE", None)
    monkeypatch.setattr(service, "_QUEUE_EVENT_LISTENER", None)

    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    execution_order: list[str] = []

    def fake_action(model_id: str, operation: str) -> None:
        assert operation == "install"
        execution_order.append(model_id)
        if model_id == "realesrgan-x2":
            first_started.set()
            assert release_first.wait(timeout=2)
        else:
            second_started.set()

    monkeypatch.setattr(service, "_action", fake_action)

    first = service.start_model_action("realesrgan-x2", "install")
    assert first_started.wait(timeout=2)
    second = service.start_model_action("realesrgan-x4", "install")

    assert first["jobId"] is not None
    assert first["position"] == 0
    assert second["jobId"] is not None
    assert second["position"] == 1
    assert not second_started.is_set()
    assert service.download_queue_snapshot(queue)["pending"][0]["modelId"] == ("realesrgan-x4")

    release_first.set()
    assert second_started.wait(timeout=2)
    _wait_until(lambda: not queue.is_busy())
    assert execution_order == ["realesrgan-x2", "realesrgan-x4"]


def test_download_snapshot_retains_fast_failures() -> None:
    from backend.models import service

    queue = ModelDownloadQueue()
    finished = threading.Event()

    def fail() -> None:
        raise RuntimeError("download host unavailable")

    queue.enqueue("model", "realesrgan-x2", fail, lambda _error: finished.set())
    assert finished.wait(timeout=2)

    snapshot = service.download_queue_snapshot(queue)
    assert snapshot["active"] == []
    assert snapshot["pending"] == []
    recent = snapshot["recent"][0]
    assert recent["modelId"] == "realesrgan-x2"
    assert recent["state"] == "failed"
    assert recent["error"] == "download host unavailable"
