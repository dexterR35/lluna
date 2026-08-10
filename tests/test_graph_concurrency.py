"""Independent branches run together; model-backed nodes still take turns."""

from __future__ import annotations

import threading
import time

import pytest
from PIL import Image

from backend.artifacts.store import ArtifactStore, DesktopGrantStore
from backend.graph.executor import RunManager
from backend.graph.schema import WorkflowDocument, WorkflowEdge, WorkflowNode


def _wait(manager, run_id, timeout=10):
    deadline = time.monotonic() + timeout
    snapshot = manager.get(run_id)
    while time.monotonic() < deadline:
        snapshot = manager.get(run_id)
        if snapshot.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return snapshot
        time.sleep(0.01)
    return snapshot


@pytest.fixture
def fan_out(monkeypatch, tmp_path):
    """load -> two independent upscales; nothing connects the two branches."""
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    source_path = tmp_path / "input.png"
    Image.new("RGBA", (4, 3), (10, 20, 30, 255)).save(source_path)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grant = DesktopGrantStore.instance().issue(source_path)
    RunManager._instance = None
    manager = RunManager.instance()

    nodes = [
        WorkflowNode(
            id="load", schema_id="lluna.input.image", parameters={"pathGrantId": grant.grant_id}
        ),
        WorkflowNode(id="left", schema_id="lluna.image.upscale", parameters={"model": "test"}),
        WorkflowNode(id="right", schema_id="lluna.image.upscale", parameters={"model": "test2"}),
    ]
    edges = [
        WorkflowEdge(
            source_node_id="load",
            source_port_id="image",
            target_node_id=target,
            target_port_id="image",
        )
        for target in ("left", "right")
    ]
    return manager, WorkflowDocument(nodes=nodes, edges=edges)


def _track_overlap(monkeypatch, manager):
    """Record how many nodes are inside _run_node simultaneously."""
    original = RunManager._run_node
    state = {"current": 0, "peak": 0}
    lock = threading.Lock()

    def traced(self, control, node, inputs, input_artifacts, cache_key, device=""):
        with lock:
            state["current"] += 1
            state["peak"] = max(state["peak"], state["current"])
        try:
            time.sleep(0.05)  # widen the window so genuine overlap is observable
            return original(self, control, node, inputs, input_artifacts, cache_key, device=device)
        finally:
            with lock:
                state["current"] -= 1

    monkeypatch.setattr(RunManager, "_run_node", traced)
    return state


def test_model_backed_nodes_never_overlap(monkeypatch, fan_out):
    """Upscale declares required_models, so the two branches must take turns."""
    manager, workflow = fan_out
    state = _track_overlap(monkeypatch, manager)

    snapshot = _wait(manager, manager.start(workflow).run_id)

    assert snapshot.status == "COMPLETED", snapshot.error
    assert state["peak"] == 1, "two model nodes held an inference device at once"


def test_both_branches_still_produce_their_output(monkeypatch, fan_out):
    manager, workflow = fan_out

    snapshot = _wait(manager, manager.start(workflow).run_id)

    assert snapshot.status == "COMPLETED", snapshot.error
    assert snapshot.nodes["left"].status in {"SUCCEEDED", "CACHED"}
    assert snapshot.nodes["right"].status in {"SUCCEEDED", "CACHED"}


def test_serial_mode_produces_the_same_result(monkeypatch, fan_out):
    """The kill switch must change timing only, never outcomes."""
    manager, workflow = fan_out
    monkeypatch.setenv("LLUNA_GRAPH_CONCURRENCY", "0")

    snapshot = _wait(manager, manager.start(workflow).run_id)

    assert snapshot.status == "COMPLETED", snapshot.error
    assert snapshot.nodes["left"].status in {"SUCCEEDED", "CACHED"}
    assert snapshot.nodes["right"].status in {"SUCCEEDED", "CACHED"}
    assert snapshot.progress == 100


def test_a_failing_branch_fails_the_run(monkeypatch, fan_out):
    """One branch blowing up must not leave the run reported as completed."""
    manager, workflow = fan_out
    original = RunManager._run_node

    def exploding(self, control, node, inputs, input_artifacts, cache_key, device=""):
        if node.id == "left":
            raise RuntimeError("branch failure")
        return original(self, control, node, inputs, input_artifacts, cache_key, device=device)

    monkeypatch.setattr(RunManager, "_run_node", exploding)

    snapshot = _wait(manager, manager.start(workflow).run_id)

    assert snapshot.status == "FAILED"
    assert snapshot.error


def test_progress_reaches_100_with_concurrent_waves(monkeypatch, fan_out):
    manager, workflow = fan_out

    snapshot = _wait(manager, manager.start(workflow).run_id)

    assert snapshot.status == "COMPLETED", snapshot.error
    assert snapshot.progress == 100
