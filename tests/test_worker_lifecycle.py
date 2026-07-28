from __future__ import annotations

import queue
import threading
import time

from backend.tools import infer_worker
from backend.tools.hardware_accelerator import HardwareAccelerator
from backend.tools.infer_client import InferClient, _JobCallbacks
from backend.tools.infer_protocol import EvtMsg, JobType, cancel, result, shutdown, start_job


class FakeHardware:
    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


def test_worker_control_loop_can_cancel_active_job(monkeypatch) -> None:
    command_queue = queue.Queue()
    event_queue = queue.Queue()
    started = threading.Event()
    cancelled = threading.Event()

    monkeypatch.setattr(infer_worker, "ensure_expandable_segments", lambda: None)
    monkeypatch.setattr(infer_worker, "empty_cuda_cache", lambda: None)
    monkeypatch.setattr(infer_worker, "_release_all_except", lambda keep=None: None)
    monkeypatch.setattr(
        HardwareAccelerator,
        "instance",
        classmethod(lambda cls: FakeHardware()),
    )

    def fake_job(
        run_id,
        payload,
        cancel_event,
        on_progress,
        heartbeat_log,
        evt_queue,
    ):
        started.set()
        if cancel_event.wait(timeout=2.0):
            cancelled.set()

    monkeypatch.setattr(infer_worker, "_job_enhance", fake_job)
    thread = threading.Thread(
        target=infer_worker.infer_worker_main,
        args=(command_queue, event_queue, True),
    )
    thread.start()
    command_queue.put(start_job(1, JobType.ENHANCE, {}))
    assert started.wait(timeout=1.0)
    command_queue.put(cancel(1))
    assert cancelled.wait(timeout=1.0)
    command_queue.put(shutdown())
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_result_waits_until_per_image_memory_is_released(monkeypatch) -> None:
    command_queue = queue.Queue()
    event_queue = queue.Queue()
    job_returned = threading.Event()
    release_started = threading.Event()
    allow_release = threading.Event()
    release_calls = []

    monkeypatch.setattr(infer_worker, "ensure_expandable_segments", lambda: None)
    monkeypatch.setattr(infer_worker, "empty_cuda_cache", lambda: None)
    monkeypatch.setattr(
        HardwareAccelerator,
        "instance",
        classmethod(lambda cls: FakeHardware()),
    )

    def fake_release(keep=None):
        release_calls.append(keep)
        if keep is None and job_returned.is_set():
            release_started.set()
            assert allow_release.wait(timeout=2.0)

    def fake_job(
        run_id,
        payload,
        cancel_event,
        on_progress,
        heartbeat_log,
        evt_queue,
    ):
        infer_worker._emit(evt_queue, result(run_id, "finished.png"))
        job_returned.set()

    monkeypatch.setattr(infer_worker, "_release_all_except", fake_release)
    monkeypatch.setattr(infer_worker, "_job_enhance", fake_job)

    thread = threading.Thread(
        target=infer_worker.infer_worker_main,
        args=(command_queue, event_queue, True),
    )
    thread.start()
    command_queue.put(
        start_job(
            7,
            JobType.ENHANCE,
            {"release_after_job": True},
        )
    )
    assert release_started.wait(timeout=1.0)

    # Live log events may arrive, but RESULT must remain hidden while model
    # release is still blocked.
    events_before_release = []
    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        try:
            events_before_release.append(event_queue.get(timeout=0.02))
        except queue.Empty:
            pass
    assert not any(kind == EvtMsg.RESULT.value for kind, _ in events_before_release)

    allow_release.set()
    kind, payload = event_queue.get(timeout=1.0)
    while kind != EvtMsg.RESULT.value:
        kind, payload = event_queue.get(timeout=1.0)
    assert payload["run_id"] == 7
    assert payload["path"] == "finished.png"
    assert release_calls[:2] == [JobType.ENHANCE.value, None]

    command_queue.put(shutdown())
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_infer_client_can_be_reset_between_test_runs(monkeypatch) -> None:
    first = InferClient.instance()
    InferClient.reset_instance_for_tests()
    second = InferClient.instance()
    assert second is not first
    InferClient.reset_instance_for_tests()


def test_shutdown_releases_waiting_job_callbacks() -> None:
    client = InferClient()
    errors = []
    completed = threading.Event()
    client._active = _JobCallbacks(
        run_id=1,
        job_type=JobType.SUBTITLE.value,
        on_error=errors.append,
        on_done=completed.set,
    )
    client.shutdown()
    assert errors == ["__cancelled__"]
    assert completed.is_set()
