from __future__ import annotations

import queue
import threading

from backend.tools import infer_worker
from backend.tools.hardware_accelerator import HardwareAccelerator
from backend.tools.infer_client import InferClient, _JobCallbacks
from backend.tools.infer_protocol import JobType, cancel, shutdown, start_job


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
