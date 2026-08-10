"""Stop must reach every worker a run owns, on whichever device it is running."""

from __future__ import annotations

import threading

import pytest

from backend.graph.executor import RunManager, _RunControl
from backend.graph.schema import WorkflowDocument
from backend.tools.inference.client import InferClient


class _FakeClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.cancelled: list[int] = []

    def cancel(self, run_id: int) -> None:
        self.cancelled.append(run_id)


@pytest.fixture
def control():
    """A live run registered with the manager, so cancel() can find it."""
    from backend.graph.executor import RunSnapshot

    snapshot = RunSnapshot(
        run_id="run-1", status="RUNNING", workflowId="wf-1", workflowHash="hash-1"
    )
    item = _RunControl(snapshot, WorkflowDocument(nodes=[], edges=[]))
    manager = RunManager.instance()
    manager._runs["run-1"] = item
    try:
        yield item
    finally:
        manager._runs.pop("run-1", None)


def test_cancel_reaches_jobs_on_every_device(control, monkeypatch):
    """With two workers, cancelling by bare id against the default client
    would leave the second GPU's job running."""
    manager = RunManager.instance()
    first, second = _FakeClient("cuda:0"), _FakeClient("cuda:1")
    control.worker_jobs.update({(first, 7), (second, 7)})

    manager.cancel("run-1")

    assert first.cancelled == [7]
    assert second.cancelled == [7], "the job on the second device was never cancelled"


def test_run_ids_are_not_confused_between_clients(control, monkeypatch):
    """Each client numbers its own jobs, so the id alone does not identify one."""
    manager = RunManager.instance()
    first, second = _FakeClient("cuda:0"), _FakeClient("cuda:1")
    control.worker_jobs.add((first, 3))

    manager.cancel("run-1")

    assert first.cancelled == [3]
    assert second.cancelled == [], "cancelled a job on a client that owned nothing"


def test_a_failing_client_does_not_stop_the_others(control, monkeypatch):
    manager = RunManager.instance()

    class _Broken(_FakeClient):
        def cancel(self, run_id: int) -> None:
            raise RuntimeError("worker already gone")

    broken, healthy = _Broken("cuda:0"), _FakeClient("cuda:1")
    control.worker_jobs.update({(broken, 1), (healthy, 2)})

    manager.cancel("run-1")

    assert healthy.cancelled == [2]


def test_finished_jobs_are_deregistered(control):
    """A stale registration would make a later Stop cancel an unrelated job."""
    client = _FakeClient("cuda:0")
    with control.lock:
        control.worker_jobs.add((client, 5))
        control.worker_jobs.discard((client, 5))

    assert control.worker_jobs == set()


def test_default_device_maps_to_the_shared_worker():
    assert InferClient.for_device("") is InferClient.instance()
    assert InferClient.for_device("cpu") is InferClient.instance()
    assert InferClient.for_device(InferClient.available_devices()[0]) is InferClient.instance()


def test_single_device_is_the_default(monkeypatch):
    monkeypatch.delenv("LLUNA_INFER_DEVICES", raising=False)
    assert InferClient.available_devices() == ("cuda:0",)


def test_multi_device_is_opt_in(monkeypatch):
    monkeypatch.setenv("LLUNA_INFER_DEVICES", "cuda:0, cuda:1")
    assert InferClient.available_devices() == ("cuda:0", "cuda:1")


def test_shutdown_all_stops_every_worker(monkeypatch):
    stopped: list[str] = []

    class _Stoppable(_FakeClient):
        def shutdown(self) -> None:
            stopped.append(self.name)

    monkeypatch.setattr(InferClient, "_instance", _Stoppable("default"))
    monkeypatch.setattr(InferClient, "_by_device", {"cuda:1": _Stoppable("cuda:1")})

    InferClient.shutdown_all()

    assert sorted(stopped) == ["cuda:1", "default"]


def test_worker_pins_itself_to_its_device_before_importing_frameworks():
    """CUDA_VISIBLE_DEVICES is ignored once torch has initialised CUDA, so the
    pinning has to be the first thing the child process does."""
    import inspect

    from backend.tools.inference import worker

    body = inspect.getsource(worker.infer_worker_main)
    statements = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith(("#", '"', "'", ")", "def ", "cmd_queue"))
    ]
    pin_index = next(i for i, line in enumerate(statements) if "CUDA_VISIBLE_DEVICES" in line)
    import_index = next(i for i, line in enumerate(statements) if line.startswith("from backend"))

    assert pin_index < import_index
