"""A transient worker failure (TIMEOUT/WORKER_CRASH/BUSY) retries up to
node_retry_limit before failing the node; a non-retryable failure never does.
"""

from __future__ import annotations

import pytest
from PIL import Image

from backend.artifacts.store import ArtifactStore, DesktopGrantStore
from backend.graph.executor import ExecutionFailure, RunManager, RunSnapshot, _RunControl
from backend.graph.schema import WorkflowDocument, WorkflowNode
from backend.tools.inference.client import InferClient
from backend.tools.inference.protocol import JobType


class _NoRetrySettings:
    class runtime:
        node_retry_limit = 0


class _RetrySettings:
    def __init__(self, limit: int) -> None:
        class _Runtime:
            node_retry_limit = limit

        self.runtime = _Runtime()


@pytest.fixture
def control():
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


class _ScriptedClient:
    """Fake InferClient whose start_job answers synchronously from a script
    of ("error", code) / ("result", path) steps, one per call."""

    def __init__(self, steps: list[tuple[str, str]]) -> None:
        self._steps = list(steps)
        self.calls = 0

    def cancel(self, run_id: int) -> None:
        pass

    def start_job(self, job_type, payload, *, on_progress, on_log, on_result, on_error, on_done, on_preview, coalesce):
        self.calls += 1
        kind, value = self._steps.pop(0)
        if kind == "error":
            on_error(value)
        else:
            on_result(value)
        on_done()
        return self.calls


def test_transient_failure_retries_then_succeeds(control, monkeypatch, tmp_path):
    manager = RunManager.instance()
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None

    output = tmp_path / "out.png"
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(output)
    client = _ScriptedClient([("error", "CRASH"), ("error", "CRASH"), ("result", str(output))])

    monkeypatch.setattr(InferClient, "for_device", lambda device: client)
    monkeypatch.setattr("backend.graph.executor.get_settings", lambda: _RetrySettings(2))
    monkeypatch.setattr("backend.graph.executor.time.sleep", lambda seconds: None)

    node = WorkflowNode(id="n-1", schema_id="lluna.image.upscale")
    result = manager._invoke_worker(
        control, node, JobType.ENHANCE, {}, str(output), [], "cache-key", device=""
    )

    assert client.calls == 3
    assert result.artifact_id


def test_transient_failure_gives_up_after_retry_limit(control, monkeypatch, tmp_path):
    manager = RunManager.instance()
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None

    client = _ScriptedClient([("error", "CRASH"), ("error", "CRASH")])

    monkeypatch.setattr(InferClient, "for_device", lambda device: client)
    monkeypatch.setattr("backend.graph.executor.get_settings", lambda: _RetrySettings(1))
    monkeypatch.setattr("backend.graph.executor.time.sleep", lambda seconds: None)

    node = WorkflowNode(id="n-1", schema_id="lluna.image.upscale")
    with pytest.raises(ExecutionFailure) as excinfo:
        manager._invoke_worker(
            control, node, JobType.ENHANCE, {}, str(tmp_path / "out.png"), [], "cache-key", device=""
        )

    assert client.calls == 2  # 1 initial attempt + 1 retry, then give up
    assert excinfo.value.code == "WORKER_CRASH"
    assert excinfo.value.retryable is True


def test_non_retryable_failure_never_retries(control, monkeypatch, tmp_path):
    manager = RunManager.instance()
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None

    client = _ScriptedClient([("error", "Prompt is empty.")])

    monkeypatch.setattr(InferClient, "for_device", lambda device: client)
    monkeypatch.setattr("backend.graph.executor.get_settings", lambda: _RetrySettings(3))
    monkeypatch.setattr("backend.graph.executor.time.sleep", lambda seconds: None)

    node = WorkflowNode(id="n-1", schema_id="lluna.generate.image")
    with pytest.raises(ExecutionFailure) as excinfo:
        manager._invoke_worker(
            control, node, JobType.GENERATE, {}, str(tmp_path / "out.png"), [], "cache-key", device=""
        )

    assert client.calls == 1
    assert excinfo.value.code == "INTERNAL"
    assert excinfo.value.retryable is False
