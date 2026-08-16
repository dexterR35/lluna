"""Workflow execution over the existing single inference-worker boundary."""

from __future__ import annotations

import base64
import hashlib
import heapq
import json
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.api.events import EventBroker
from backend.artifacts.models import ArtifactRecord
from backend.artifacts.store import ArtifactStore, DesktopGrantStore
from backend.configuration.service import get_settings
from backend.graph.cache import build_cache_key, stable_hash
from backend.graph.compiler import compile_workflow
from backend.graph.registry import NODE_REGISTRY, get_node
from backend.graph.scheduler import (
    LIGHT,
    DeviceScheduler,
    concurrency_enabled,
    execution_waves,
    node_kind,
    plan_concurrency,
)
from backend.graph.schema import WorkflowDocument, WorkflowNode
from backend.tools.inference.protocol import JobType


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    PAUSED = "PAUSED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class NodeRun(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)
    node_id: str
    status: str = "IDLE"
    progress: int = 0
    message: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    save_items: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunSnapshot(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)
    run_id: str
    workflow_id: str
    workflow_hash: str
    status: RunStatus = RunStatus.QUEUED
    priority: int = 0
    queue_position: int | None = None
    progress: int = 0
    current_node_id: str | None = None
    nodes: dict[str, NodeRun] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ExecutionFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _artifact_values(value: Any) -> list[ArtifactRecord]:
    """Flatten an execution value while preserving its artifact order."""
    if isinstance(value, ArtifactRecord):
        return [value]
    if isinstance(value, dict):
        return [artifact for item in value.values() for artifact in _artifact_values(item)]
    if isinstance(value, (list, tuple)):
        return [artifact for item in value for artifact in _artifact_values(item)]
    return []


def _primary_artifact_values(value: Any) -> list[ArtifactRecord]:
    """Return the visual/main output used by the node preview and status UI."""
    if isinstance(value, dict):
        for port_id in ("image", "video", "mask", "alpha", "output"):
            if port_id in value:
                return _primary_artifact_values(value[port_id])
        first = next(iter(value.values()), None)
        return _primary_artifact_values(first)
    if isinstance(value, (list, tuple)):
        return [item for entry in value for item in _primary_artifact_values(entry)]
    return [value] if isinstance(value, ArtifactRecord) else []


def _subtitle_options(parameters: dict[str, Any]) -> dict[str, Any]:
    """Translate graph-facing video controls to the subtitle service contract."""
    options = dict(parameters.get("options") or {})
    if "subAreas" in parameters:
        options["sub_areas"] = parameters["subAreas"]
    return options


def _model_revision_for_node(node: WorkflowNode) -> str:
    """Fingerprint the node's selected custom model, if any.

    Built-in models are immutable once downloaded, so an empty revision is
    fine for them. A *custom* model's on-disk files can be replaced in place
    (re-import, reconfigure) while keeping the same id, which would otherwise
    let a stale cached artifact survive a model update - see
    `DynamicModelRegistry.revision_stamp`.
    """
    parts: list[str] = []
    model_value = str(node.parameters.get("model") or "")
    ids = [model_value.removeprefix("custom:")] if model_value.startswith("custom:") else []
    # A LoRA changes the output as surely as the base model does, and its files
    # can be replaced in place just the same, so every selected adapter has to
    # contribute to the fingerprint. (Which LoRAs and at what weight is already
    # covered: node.parameters is part of the cache key.)
    for item in node.parameters.get("loras") or []:
        if isinstance(item, str):
            ids.append(item.removeprefix("custom:"))
        elif isinstance(item, dict):
            raw = str(item.get("modelId") or item.get("model_id") or item.get("id") or "")
            if raw:
                ids.append(raw.removeprefix("custom:"))
    if not ids:
        return ""
    try:
        from backend.models.dynamic_registry import DynamicModelRegistry

        registry = DynamicModelRegistry.instance()
        parts = [f"{model_id}:{registry.revision_stamp(model_id)}" for model_id in ids]
    except (ImportError, OSError, ValueError):
        return ""
    return "|".join(parts)


class _Progress:
    """Completed-node counter, since concurrent waves have no single index."""

    def __init__(self, total: int) -> None:
        self._total = max(1, total)
        self._done = 0
        self._lock = threading.Lock()

    def advance(self, control: "_RunControl") -> None:
        with self._lock:
            self._done += 1
            percent = int(self._done * 100 / self._total)
        with control.lock:
            control.snapshot.progress = min(100, percent)


class _RunControl:
    def __init__(
        self,
        snapshot: RunSnapshot,
        workflow: WorkflowDocument,
        *,
        mode: str = "all",
        selected_node_ids: list[str] | None = None,
        force: bool = False,
    ) -> None:
        self.snapshot = snapshot
        self.workflow = workflow.model_copy(deep=True)
        self.mode = mode
        self.selected_node_ids = list(selected_node_ids or [])
        self.force = force
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.condition = threading.Condition()
        # Worker jobs this run currently owns, as (client, worker run id). A run
        # can hold more than one at a time when several inference devices are
        # configured, and each client numbers its jobs independently, so cancelling
        # by bare run id against the default client would miss - or worse, hit the
        # wrong job. Guarded by `lock`.
        self.worker_jobs: set[tuple[Any, int]] = set()
        self.lock = threading.RLock()


class RunManager:
    _instance: "RunManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._runs: dict[str, _RunControl] = {}
        self._lock = threading.RLock()
        self._queue_condition = threading.Condition(self._lock)
        self._queue: list[tuple[int, int, str]] = []
        self._queue_sequence = 0
        self._active_run_id: str | None = None
        self._dispatcher: threading.Thread | None = None
        self._shutdown = False
        self._events = EventBroker.instance()
        self._artifacts = ArtifactStore.instance()
        self._grants = DesktopGrantStore.instance()
        self._cache_path = self._artifacts.root / "graph-cache.json"
        self._cache_lock = threading.RLock()
        self._cache = self._load_cache()

    @classmethod
    def instance(cls) -> "RunManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_cache(self) -> dict[str, str]:
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save_cache(self) -> None:
        from backend.core.atomic import atomic_write_json

        atomic_write_json(self._cache_path, self._cache)

    def start(
        self,
        workflow: WorkflowDocument,
        *,
        mode: str = "all",
        selected_node_ids: list[str] | None = None,
        force: bool = False,
        queue_front: bool = False,
    ) -> RunSnapshot:
        plan = compile_workflow(
            workflow, mode=mode, selected_node_ids=selected_node_ids, check_model_availability=True
        )
        if not plan.validation.valid:
            first_error = next(
                (issue for issue in plan.validation.issues if issue.severity == "error"),
                None,
            )
            raise ExecutionFailure(
                "VALIDATION",
                first_error.message if first_error else "Workflow validation failed.",
            )
        if not plan.steps:
            raise ExecutionFailure("EMPTY_PLAN", "Nothing to run from the selected node.")
        run_id = str(uuid4())
        frozen_graph = workflow.model_dump(mode="json", by_alias=True)
        graph_bytes = json.dumps(
            frozen_graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        priority = -1 if queue_front else 0
        generation_history = []
        workflow_nodes = {item.id: item for item in workflow.nodes}
        for step in plan.steps:
            if step.schema_id not in {"lluna.generate.image", "lluna.generate.image.edit"}:
                continue
            item = workflow_nodes.get(step.node_id)
            if item is None:
                continue
            prompt = str(item.parameters.get("prompt") or "").strip()
            for edge in workflow.edges:
                if edge.target_node_id == item.id and edge.target_port_id == "prompt":
                    source = workflow_nodes.get(edge.source_node_id)
                    if source is not None:
                        prompt = str(source.parameters.get("value") or prompt).strip()
                        break
            generation_history.append(
                {
                    "nodeId": item.id,
                    "schemaId": item.schema_id,
                    "model": str(item.parameters.get("model") or ""),
                    "prompt": prompt,
                    "negativePrompt": str(item.parameters.get("negativePrompt") or "").strip(),
                    "seed": item.parameters.get("seed", -1),
                }
            )
        snapshot = RunSnapshot(
            run_id=run_id,
            workflow_id=workflow.project_id,
            workflow_hash=hashlib.sha256(graph_bytes).hexdigest(),
            priority=priority,
            metadata={"generations": generation_history},
            nodes={step.node_id: NodeRun(node_id=step.node_id) for step in plan.steps},
        )
        control = _RunControl(
            snapshot,
            workflow,
            mode=mode,
            selected_node_ids=selected_node_ids,
            force=force,
        )
        with self._queue_condition:
            self._runs[run_id] = control
            self._queue_sequence += 1
            heapq.heappush(self._queue, (priority, self._queue_sequence, run_id))
            self._refresh_queue_positions_locked()
            self._ensure_dispatcher_locked()
            self._queue_condition.notify()
        self._events.publish(
            "run.queued",
            run_id=run_id,
            payload={
                "workflowId": workflow.project_id,
                "workflowHash": snapshot.workflow_hash,
                "mode": mode,
                "priority": priority,
                "queuePosition": snapshot.queue_position,
            },
        )
        return snapshot.model_copy(deep=True)

    def get(self, run_id: str) -> RunSnapshot:
        with self._lock:
            control = self._runs.get(run_id)
        if control is None:
            raise KeyError(run_id)
        with self._lock, control.lock:
            self._refresh_queue_positions_locked()
            return control.snapshot.model_copy(deep=True)

    def queue_snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_queue_positions_locked()
            running = self._runs.get(self._active_run_id or "")
            pending = [
                self._runs[run_id].snapshot.model_copy(deep=True)
                for _, _, run_id in sorted(self._queue)
                if run_id in self._runs and self._runs[run_id].snapshot.status == RunStatus.QUEUED
            ]
            return {
                "running": running.snapshot.model_copy(deep=True) if running else None,
                "pending": pending,
            }

    def history(self, *, limit: int | None = None) -> list[RunSnapshot]:
        configured_limit = get_settings().runtime.run_history_limit
        effective_limit = max(1, min(limit or configured_limit, configured_limit))
        with self._lock:
            completed = [
                control.snapshot.model_copy(deep=True)
                for control in self._runs.values()
                if control.snapshot.status
                in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
            ]
        completed.sort(key=lambda item: item.completed_at or item.created_at, reverse=True)
        return completed[:effective_limit]

    def pause(self, run_id: str) -> RunSnapshot:
        control = self._control(run_id)
        control.pause.set()
        with control.lock:
            if control.snapshot.status == RunStatus.RUNNING:
                control.snapshot.status = RunStatus.PAUSE_REQUESTED
        self._events.publish("run.pause_requested", run_id=run_id)
        return self.get(run_id)

    def resume(self, run_id: str) -> RunSnapshot:
        control = self._control(run_id)
        control.pause.clear()
        with control.condition:
            control.condition.notify_all()
        with control.lock:
            if control.snapshot.status in {RunStatus.PAUSED, RunStatus.PAUSE_REQUESTED}:
                control.snapshot.status = RunStatus.RUNNING
        self._events.publish("run.resumed", run_id=run_id)
        return self.get(run_id)

    def cancel(self, run_id: str) -> RunSnapshot:
        control = self._control(run_id)
        control.cancel.set()
        with control.lock:
            queued = control.snapshot.status == RunStatus.QUEUED
            control.snapshot.status = RunStatus.CANCELLED if queued else RunStatus.CANCEL_REQUESTED
            if queued:
                control.snapshot.completed_at = datetime.now(timezone.utc)
                control.snapshot.error = {
                    "code": "CANCELLED",
                    "message": "Run cancelled before execution.",
                    "retryable": False,
                }
            worker_jobs = tuple(control.worker_jobs)
        for client, worker_run_id in worker_jobs:
            try:
                client.cancel(worker_run_id)
            except RuntimeError:
                pass
        with control.condition:
            control.condition.notify_all()
        with self._queue_condition:
            self._refresh_queue_positions_locked()
            self._queue_condition.notify_all()
        self._events.publish(
            "run.cancelled" if queued else "run.cancel_requested",
            run_id=run_id,
            payload=control.snapshot.error or {},
        )
        return self.get(run_id)

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
            self._save_cache()

    def shutdown(self) -> None:
        with self._queue_condition:
            self._shutdown = True
            controls = tuple(self._runs.values())
            self._queue_condition.notify_all()
        for control in controls:
            control.cancel.set()
        try:
            from backend.tools.inference.client import InferClient

            InferClient.shutdown_all()
        except (ImportError, RuntimeError):
            pass

    def _ensure_dispatcher_locked(self) -> None:
        if self._dispatcher is not None and self._dispatcher.is_alive():
            return
        self._shutdown = False
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop,
            name="workflow-queue",
            daemon=True,
        )
        self._dispatcher.start()

    def _dispatch_loop(self) -> None:
        while True:
            with self._queue_condition:
                while not self._queue and not self._shutdown:
                    self._queue_condition.wait()
                if self._shutdown:
                    return
                _, _, run_id = heapq.heappop(self._queue)
                control = self._runs.get(run_id)
                if control is None or control.cancel.is_set():
                    self._refresh_queue_positions_locked()
                    continue
                self._active_run_id = run_id
                control.snapshot.queue_position = None
                self._refresh_queue_positions_locked()
            try:
                self._execute(control)
            finally:
                with self._queue_condition:
                    self._active_run_id = None
                    self._prune_history_locked()
                    self._refresh_queue_positions_locked()
                    self._queue_condition.notify_all()

    def _refresh_queue_positions_locked(self) -> None:
        for control in self._runs.values():
            if control.snapshot.status == RunStatus.QUEUED:
                control.snapshot.queue_position = None
        position = 1
        for _, _, run_id in sorted(self._queue):
            control = self._runs.get(run_id)
            if control is None or control.cancel.is_set():
                continue
            if control.snapshot.status == RunStatus.QUEUED:
                control.snapshot.queue_position = position
                position += 1

    def _prune_history_locked(self) -> None:
        limit = get_settings().runtime.run_history_limit
        terminal = sorted(
            (
                control.snapshot.completed_at or control.snapshot.created_at,
                run_id,
            )
            for run_id, control in self._runs.items()
            if control.snapshot.status
            in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
        )
        for _, run_id in terminal[:-limit]:
            self._runs.pop(run_id, None)

    def _control(self, run_id: str) -> _RunControl:
        with self._lock:
            control = self._runs.get(run_id)
        if control is None:
            raise KeyError(run_id)
        return control

    def _execute(self, control: _RunControl) -> None:
        snapshot = control.snapshot
        workflow = control.workflow
        plan = compile_workflow(
            workflow,
            mode=control.mode,
            selected_node_ids=control.selected_node_ids,
            check_model_availability=True,
        )
        nodes = {node.id: node for node in workflow.nodes}
        incoming: dict[str, dict[str, list[tuple[str, str]]]] = {}
        for edge in workflow.edges:
            incoming.setdefault(edge.target_node_id, {}).setdefault(
                edge.target_port_id, []
            ).append((edge.source_node_id, edge.source_port_id))
        active = {step.node_id for step in plan.steps}
        with control.lock:
            snapshot.status = RunStatus.RUNNING
            snapshot.started_at = datetime.now(timezone.utc)
        self._events.publish("run.started", run_id=snapshot.run_id)
        try:
            values = self._boundary_values(workflow, active)
            total = max(len(plan.steps), 1)
            self._run_steps(control, plan, nodes, incoming, values, total)
            with control.lock:
                snapshot.status = RunStatus.COMPLETED
                snapshot.progress = 100
                snapshot.completed_at = datetime.now(timezone.utc)
            self._events.publish(
                "run.completed",
                run_id=snapshot.run_id,
                payload={"artifactIds": snapshot.artifact_ids},
            )
        except ExecutionFailure as exc:
            cancelled = exc.code == "CANCELLED"
            node_status = "CANCELLED" if cancelled else "FAILED"
            with control.lock:
                snapshot.status = RunStatus.CANCELLED if cancelled else RunStatus.FAILED
                snapshot.completed_at = datetime.now(timezone.utc)
                snapshot.error = {"code": exc.code, "message": str(exc), "retryable": exc.retryable}
                if snapshot.current_node_id and snapshot.current_node_id in snapshot.nodes:
                    state = snapshot.nodes[snapshot.current_node_id]
                    state.status = node_status
                    state.message = str(exc)
                    state.completed_at = snapshot.completed_at
            if snapshot.current_node_id:
                self._events.publish(
                    "node.cancelled" if cancelled else "node.failed",
                    run_id=snapshot.run_id,
                    node_id=snapshot.current_node_id,
                    payload=snapshot.error or {},
                )
            self._events.publish(
                "run.cancelled" if cancelled else "run.failed",
                run_id=snapshot.run_id,
                node_id=snapshot.current_node_id,
                payload=snapshot.error or {},
            )
        except Exception as exc:
            error = {"code": "INTERNAL", "message": str(exc), "retryable": False}
            with control.lock:
                snapshot.status = RunStatus.FAILED
                snapshot.completed_at = datetime.now(timezone.utc)
                snapshot.error = error
                if snapshot.current_node_id and snapshot.current_node_id in snapshot.nodes:
                    state = snapshot.nodes[snapshot.current_node_id]
                    state.status = "FAILED"
                    state.message = str(exc)
                    state.completed_at = snapshot.completed_at
            if snapshot.current_node_id:
                self._events.publish(
                    "node.failed",
                    run_id=snapshot.run_id,
                    node_id=snapshot.current_node_id,
                    payload=error,
                )
            self._events.publish(
                "run.failed",
                run_id=snapshot.run_id,
                node_id=snapshot.current_node_id,
                payload=error,
            )

    def _run_steps(
        self,
        control: _RunControl,
        plan: Any,
        nodes: dict[str, WorkflowNode],
        incoming: dict[str, dict[str, list[tuple[str, str]]]],
        values: dict[tuple[str, str], Any],
        total: int,
    ) -> None:
        """Execute every planned node, running independent branches together.

        Nodes are grouped into dependency waves; within a wave, order no longer
        matters by construction, so they are handed to a pool. Admission is what
        keeps this safe: `DeviceScheduler` allows only one model-backed node onto
        an inference device at a time, so concurrency buys overlap between CPU
        work and GPU work rather than two pipelines fighting over VRAM.
        """
        order = [step.node_id for step in plan.steps]
        kinds = {
            node_id: node_kind(NODE_REGISTRY[nodes[node_id].schema_id]) for node_id in order
        }
        waves = execution_waves(order, control.workflow.edges)
        scheduler = DeviceScheduler(heavy_devices=self._heavy_devices())
        values_lock = threading.Lock()
        progress = _Progress(total)

        for wave in waves:
            workers = plan_concurrency(wave, kinds, scheduler) if concurrency_enabled() else 1
            if workers <= 1 or len(wave) == 1:
                for node_id in wave:
                    self._run_step(
                        control, nodes[node_id], incoming, values, values_lock, scheduler, kinds
                    )
                    progress.advance(control)
                continue
            # A failure in any branch must stop the others rather than let the run
            # limp on; the cancel flag is the same one the Stop button sets.
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="lluna-node") as pool:
                futures = {
                    pool.submit(
                        self._run_step,
                        control,
                        nodes[node_id],
                        incoming,
                        values,
                        values_lock,
                        scheduler,
                        kinds,
                    ): node_id
                    for node_id in wave
                }
                failure: BaseException | None = None
                for future in as_completed(futures):
                    try:
                        future.result()
                    except BaseException as exc:  # noqa: BLE001 - re-raised below
                        if failure is None:
                            failure = exc
                            control.cancel.set()
                    else:
                        progress.advance(control)
            if failure is not None:
                raise failure

    def _heavy_devices(self) -> tuple[str, ...]:
        """Devices that may hold a model-backed node concurrently.

        One entry means today's behaviour exactly: heavy nodes take turns. The
        shared inference worker is a single process serving one job at a time, so
        a second GPU only becomes a second slot once a worker is pinned to it -
        see InferClient.for_device().
        """
        from backend.tools.inference.client import InferClient

        return InferClient.available_devices()

    def _run_step(
        self,
        control: _RunControl,
        node: WorkflowNode,
        incoming: dict[str, dict[str, list[tuple[str, str]]]],
        values: dict[tuple[str, str], Any],
        values_lock: threading.Lock,
        scheduler: DeviceScheduler,
        kinds: dict[str, str],
    ) -> None:
        snapshot = control.snapshot
        self._wait_if_paused(control)
        if control.cancel.is_set():
            raise ExecutionFailure("CANCELLED", "Run cancelled.")
        definition = NODE_REGISTRY[node.schema_id]
        input_values: dict[str, Any] = {}
        with values_lock:
            for port_id, sources in incoming.get(node.id, {}).items():
                connected = [values[source] for source in sources if source in values]
                if not connected:
                    continue
                if len(connected) == 1:
                    input_values[port_id] = connected[0]
                    continue
                combined: list[Any] = []
                for value in connected:
                    combined.extend(value if isinstance(value, (list, tuple)) else [value])
                input_values[port_id] = combined
        input_artifacts = _artifact_values(input_values)
        input_hashes = [item.content_hash for item in input_artifacts]
        if "llava" in input_values:
            input_hashes.append(f"llava:{stable_hash(input_values['llava'])}")
        cache_key = build_cache_key(
            node,
            input_hashes,
            model_revision=_model_revision_for_node(node),
        )
        has_batch_input = any(isinstance(value, (list, tuple)) for value in input_values.values())
        with self._cache_lock:
            cached_id = (
                self._cache.get(cache_key)
                if get_settings().runtime.smart_cache_enabled
                and not control.force
                and definition.cache_policy == "content-addressed"
                and not has_batch_input
                else None
            )
        result = None
        ran = False
        if cached_id:
            try:
                artifact = self._artifacts.get(cached_id)
                result = artifact
                self._node_state(control, node.id, "CACHED", 100, "Loaded from cache")
                with control.lock:
                    control.snapshot.nodes[node.id].artifact_ids = [artifact.artifact_id]
                self._events.publish(
                    "node.cached",
                    run_id=snapshot.run_id,
                    node_id=node.id,
                    payload={"artifactIds": [artifact.artifact_id]},
                )
                ran = True
            except (KeyError, FileNotFoundError):
                ran = False
        if not ran:
            # The slot is held only around the work itself: cache hits and input
            # assembly must never occupy a device other nodes are waiting for.
            with scheduler.slot(kinds.get(node.id, LIGHT)) as device:
                if control.cancel.is_set():
                    raise ExecutionFailure("CANCELLED", "Run cancelled.")
                result = self._run_node(
                    control, node, input_values, input_artifacts, cache_key, device=device
                )
        output_ports = definition.outputs
        with values_lock:
            if isinstance(result, dict) and not isinstance(result, ArtifactRecord):
                for port_id, value in result.items():
                    values[(node.id, port_id)] = value
            elif output_ports and result is not None:
                for port in output_ports:
                    values[(node.id, port.id)] = result
        result_artifacts = _artifact_values(result)
        if result_artifacts:
            with control.lock:
                snapshot.artifact_ids.extend(
                    artifact.artifact_id for artifact in result_artifacts
                )
            if isinstance(result, ArtifactRecord) and definition.cache_policy == "content-addressed":
                with self._cache_lock:
                    self._cache[cache_key] = result.artifact_id
                    self._save_cache()

    def _boundary_values(
        self,
        workflow: WorkflowDocument,
        active: set[str],
    ) -> dict[tuple[str, str], Any]:
        """Resolve stored outputs entering the plan without executing their source nodes."""
        nodes = {node.id: node for node in workflow.nodes}
        values: dict[tuple[str, str], Any] = {}
        for edge in workflow.edges:
            if edge.target_node_id not in active or edge.source_node_id in active:
                continue
            source = nodes.get(edge.source_node_id)
            definition = NODE_REGISTRY.get(source.schema_id) if source else None
            if source is None or definition is None:
                continue
            if definition.adapter == "literal":
                value = source.parameters.get("value")
            elif definition.adapter == "llava_config":
                value = dict(source.parameters)
            else:
                result = source.result or {}
                outputs = result.get("outputs")
                value = outputs.get(edge.source_port_id) if isinstance(outputs, dict) else None
                if value is None:
                    value = result.get(edge.source_port_id, result.get("value"))
                if value is None:
                    artifact_ids = result.get("artifactIds") or result.get("artifact_ids") or []
                    if artifact_ids:
                        try:
                            artifacts = [
                                self._artifacts.get(str(artifact_id))
                                for artifact_id in artifact_ids
                            ]
                            value = artifacts if len(artifacts) > 1 else artifacts[-1]
                            if (
                                source.schema_id == "lluna.mask.select_object"
                                and edge.source_port_id == "source_image"
                            ):
                                mask = artifacts[-1]
                                value = next(
                                    (
                                        self._artifacts.get(input_id)
                                        for input_id in mask.input_artifact_ids
                                    ),
                                    None,
                                )
                        except (KeyError, FileNotFoundError) as exc:
                            raise ExecutionFailure(
                                "BOUNDARY_INPUT_UNAVAILABLE",
                                "Required input has no completed output.",
                            ) from exc
            if value is not None:
                values[(source.id, edge.source_port_id)] = value
        return values

    def _wait_if_paused(self, control: _RunControl) -> None:
        if not control.pause.is_set():
            return
        with control.lock:
            control.snapshot.status = RunStatus.PAUSED
        self._events.publish("run.paused", run_id=control.snapshot.run_id)
        with control.condition:
            while control.pause.is_set() and not control.cancel.is_set():
                control.condition.wait(timeout=0.5)

    def _node_state(
        self, control: _RunControl, node_id: str, status: str, progress: int, message: str = ""
    ) -> None:
        with control.lock:
            state = control.snapshot.nodes[node_id]
            state.status, state.progress, state.message = (
                status,
                max(0, min(100, progress)),
                message,
            )
            if status == "RUNNING" and state.started_at is None:
                state.started_at = datetime.now(timezone.utc)
            if status in {"SUCCEEDED", "FAILED", "CANCELLED", "CACHED"}:
                state.completed_at = datetime.now(timezone.utc)
            control.snapshot.current_node_id = node_id

    def _run_node(
        self,
        control: _RunControl,
        node: WorkflowNode,
        inputs: dict[str, Any],
        input_artifacts: list[ArtifactRecord],
        cache_key: str,
        device: str = "",
    ) -> Any:
        definition = NODE_REGISTRY[node.schema_id]
        run_id = control.snapshot.run_id
        self._node_state(control, node.id, "RUNNING", 0)
        self._events.publish(
            "node.started", run_id=run_id, node_id=node.id, payload={"schemaId": node.schema_id}
        )
        if definition.adapter == "load_images":
            result = self._load_granted_media_batch(node)
        elif definition.adapter in {"load_image", "load_video", "load_mask"}:
            result = self._load_granted_media(node)
        elif definition.adapter == "literal":
            result = {definition.outputs[0].id: node.parameters.get("value")}
        elif definition.adapter == "llava_config":
            result = {definition.outputs[0].id: dict(node.parameters)}
        elif definition.adapter == "passthrough":
            result = next(iter(inputs.values()))
        elif definition.adapter == "save":
            result = self._save_output(control, node, next(iter(inputs.values())))
        elif any(isinstance(value, (list, tuple)) for value in inputs.values()):
            result = self._run_batch_node(control, node, inputs, device=device)
        elif definition.adapter == "composite":
            result = self._composite_images(
                control,
                node,
                inputs,
                input_artifacts,
                cache_key,
            )
        elif definition.adapter == "image_effects":
            result = self._apply_image_effects(
                control,
                node,
                inputs,
                input_artifacts,
                cache_key,
            )
        elif definition.adapter == "controlnet":
            # Emits a description, not an artifact: the generation node it feeds
            # is what actually loads the ControlNet, because only there is the
            # base model known and the pairing checkable.
            source = inputs.get("image")
            if not isinstance(source, ArtifactRecord):
                raise ExecutionFailure(
                    "MISSING_INPUT", "ControlNet needs a control map on its image input."
                )
            model_id = str(node.parameters.get("model") or "").strip()
            if not model_id:
                raise ExecutionFailure(
                    "MISSING_MODEL",
                    "Choose a ControlNet. Install one from Settings -> Models -> Add model.",
                )
            result = {
                "control": {
                    "modelId": model_id,
                    "strength": float(node.parameters.get("strength", 1.0)),
                    "start": float(node.parameters.get("start", 0.0)),
                    "end": float(node.parameters.get("end", 1.0)),
                    "imagePath": source.path,
                }
            }
        elif definition.adapter == "control_map":
            result = self._build_control_map(
                control,
                node,
                inputs,
                input_artifacts,
                cache_key,
            )
        else:
            result = self._run_inference(
                control, node, inputs, input_artifacts, cache_key, device=device
            )
        if node.schema_id == "lluna.mask.select_object" and isinstance(
            result, ArtifactRecord
        ):
            source_image = inputs.get("image")
            if isinstance(source_image, ArtifactRecord):
                # The mask stays primary for persistence and preview. The
                # original image is also exposed as a downstream port so LaMa
                # can be wired entirely from Select Object.
                result = {"mask": result, "source_image": source_image}
        self._node_state(control, node.id, "SUCCEEDED", 100)
        artifact_ids = [artifact.artifact_id for artifact in _primary_artifact_values(result)]
        with control.lock:
            control.snapshot.nodes[node.id].artifact_ids = artifact_ids
        self._events.publish(
            "node.completed", run_id=run_id, node_id=node.id, payload={"artifactIds": artifact_ids}
        )
        return result

    def _run_batch_node(
        self,
        control: _RunControl,
        node: WorkflowNode,
        inputs: dict[str, Any],
        *,
        device: str = "",
    ) -> Any:
        """Map a batch-capable node over ordered inputs using ZIP semantics."""
        lists = {
            name: list(value) for name, value in inputs.items() if isinstance(value, (list, tuple))
        }
        lengths = {len(value) for value in lists.values()}
        if not lengths or 0 in lengths:
            raise ExecutionFailure("EMPTY_BATCH", "The image queue is empty.")
        if len(lengths) != 1:
            raise ExecutionFailure(
                "BATCH_LENGTH_MISMATCH",
                "Connected image queues must contain the same number of items.",
            )
        count = lengths.pop()
        outputs: list[Any] = []
        definition = NODE_REGISTRY[node.schema_id]
        model_revision = _model_revision_for_node(node)
        for index in range(count):
            self._wait_if_paused(control)
            if control.cancel.is_set():
                raise ExecutionFailure("CANCELLED", "Run cancelled.")
            scalar_inputs = {
                name: lists[name][index] if name in lists else value
                for name, value in inputs.items()
            }
            scalar_artifacts = _artifact_values(scalar_inputs)
            input_signatures = [
                f"{name}:{artifact.content_hash}"
                for name, value in scalar_inputs.items()
                for artifact in _artifact_values(value)
            ]
            if "llava" in scalar_inputs:
                input_signatures.append(
                    f"llava:{stable_hash(scalar_inputs['llava'])}"
                )
            item_cache_key = build_cache_key(
                node, input_signatures, model_revision=model_revision
            )
            artifact = None
            if (
                get_settings().runtime.smart_cache_enabled
                and not control.force
                and definition.cache_policy == "content-addressed"
            ):
                cached_id = self._cache.get(item_cache_key)
                if cached_id:
                    try:
                        artifact = self._artifacts.get(cached_id)
                    except (KeyError, FileNotFoundError):
                        artifact = None
            if artifact is None:
                progress_offset = int(index * 100 / count)
                progress_span = 100 / count
                if definition.adapter == "composite":
                    artifact = self._composite_images(
                        control,
                        node,
                        scalar_inputs,
                        scalar_artifacts,
                        item_cache_key,
                        progress_offset=progress_offset,
                        progress_span=progress_span,
                        item_index=index,
                        item_count=count,
                    )
                elif definition.adapter == "image_effects":
                    artifact = self._apply_image_effects(
                        control,
                        node,
                        scalar_inputs,
                        scalar_artifacts,
                        item_cache_key,
                        progress_offset=progress_offset,
                        progress_span=progress_span,
                        item_index=index,
                        item_count=count,
                    )
                else:
                    artifact = self._run_inference(
                        control,
                        node,
                        scalar_inputs,
                        scalar_artifacts,
                        item_cache_key,
                        progress_offset=progress_offset,
                        progress_span=progress_span,
                        item_index=index,
                        item_count=count,
                        device=device,
                    )
                if definition.cache_policy == "content-addressed":
                    with self._cache_lock:
                        self._cache[item_cache_key] = artifact.artifact_id
                        self._save_cache()
            else:
                progress = int((index + 1) * 100 / count)
                self._node_state(
                    control,
                    node.id,
                    "RUNNING",
                    progress,
                    f"Item {index + 1} of {count} loaded from cache",
                )
                self._events.publish(
                    "node.progress",
                    run_id=control.snapshot.run_id,
                    node_id=node.id,
                    payload={
                        "progress": progress,
                        "itemIndex": index,
                        "itemCount": count,
                        "cached": True,
                        "message": f"Item {index + 1} of {count} loaded from cache",
                    },
                )
            outputs.append(artifact)
        if outputs and all(isinstance(item, dict) for item in outputs):
            keys = tuple(outputs[0].keys())
            return {key: [item[key] for item in outputs] for key in keys}
        return outputs

    def _resolve_grant(self, grant_id: str, *, mode: str, empty_message: str) -> Path:
        if not grant_id:
            raise ExecutionFailure("MISSING_INPUT", empty_message)
        try:
            return self._grants.resolve(grant_id, mode=mode)
        except PermissionError as exc:
            raise ExecutionFailure(
                "EXPIRED_GRANT",
                "The selected file expired after restart. Choose the file again on this node.",
            ) from exc

    def _load_granted_media(self, node: WorkflowNode) -> ArtifactRecord:
        persisted_ids = (
            (node.result or {}).get("artifactIds") or (node.result or {}).get("artifact_ids") or []
        )
        persisted = None
        if persisted_ids:
            try:
                persisted = self._artifacts.get(str(persisted_ids[-1]))
            except (KeyError, FileNotFoundError):
                persisted = None

        grant_id = str(node.parameters.get("pathGrantId") or "")
        if grant_id:
            try:
                path = self._grants.resolve(grant_id, mode="read")
            except PermissionError as exc:
                if persisted is not None:
                    return persisted
                raise ExecutionFailure(
                    "EXPIRED_GRANT",
                    "The selected file expired after restart. Choose the file again on this node.",
                ) from exc
            try:
                return self._artifacts.register_source(path)
            except FileNotFoundError as exc:
                if persisted is not None:
                    return persisted
                raise ExecutionFailure(
                    "MISSING_FILE", f"The selected file is missing: {path}"
                ) from exc

        if persisted is not None:
            return persisted
        raise ExecutionFailure("MISSING_INPUT", "Choose a local file for this node.")

    def _load_granted_media_batch(self, node: WorkflowNode) -> list[ArtifactRecord]:
        persisted_ids = (
            (node.result or {}).get("artifactIds") or (node.result or {}).get("artifact_ids") or []
        )
        persisted: list[ArtifactRecord] = []
        for artifact_id in persisted_ids:
            try:
                persisted.append(self._artifacts.get(str(artifact_id)))
            except (KeyError, FileNotFoundError):
                persisted = []
                break

        grant_ids = node.parameters.get("pathGrantIds") or []
        if not isinstance(grant_ids, list):
            raise ExecutionFailure(
                "INVALID_BATCH",
                "Load Images expects an ordered list of desktop file grants.",
            )
        if len(grant_ids) > 10:
            raise ExecutionFailure(
                "BATCH_TOO_LARGE",
                "Load Images accepts at most 10 images.",
            )
        if grant_ids:
            artifacts: list[ArtifactRecord] = []
            try:
                for grant_id in grant_ids:
                    path = self._grants.resolve(str(grant_id), mode="read")
                    artifacts.append(self._artifacts.register_source(path))
                return artifacts
            except (PermissionError, FileNotFoundError) as exc:
                if persisted:
                    return persisted
                raise ExecutionFailure(
                    "EXPIRED_GRANT",
                    "One or more selected files expired after restart. Choose the files again.",
                ) from exc
        if persisted:
            return persisted
        raise ExecutionFailure("EMPTY_BATCH", "Choose one or more local images.")

    @staticmethod
    def _safe_file_stem(value: str) -> str:
        stem = Path(value).stem.strip()
        cleaned = "".join(
            "_" if character in '<>:"/\\|?*' or ord(character) < 32 else character
            for character in stem
        )
        return cleaned.strip(" .") or "lluna-output"

    @staticmethod
    def _operation_suffix(schema_id: str) -> str:
        return {
            "lluna.image.remove_text": "nosub",
            "lluna.video.remove_text": "nosub",
            "lluna.image.upscale": "upscale",
            "lluna.image.low_light": "lowlight",
        }.get(schema_id, "")

    def _lineage_file_name(
        self,
        control: _RunControl,
        artifact: ArtifactRecord,
        used_names: set[str],
    ) -> str:
        schemas_by_node = {item.id: item.schema_id for item in control.workflow.nodes}
        suffixes: list[str] = []
        source_name = Path(artifact.path).name
        current = artifact
        seen_artifacts: set[str] = set()
        while current.artifact_id not in seen_artifacts:
            seen_artifacts.add(current.artifact_id)
            schema_id = current.creating_schema_id or schemas_by_node.get(
                current.creating_node_id or "", ""
            )
            suffix = self._operation_suffix(schema_id)
            if suffix and suffix not in suffixes:
                suffixes.append(suffix)
            if current.original_source_path:
                source_name = Path(current.original_source_path).name
                break
            next_artifact = None
            for input_id in current.input_artifact_ids:
                try:
                    candidate = self._artifacts.get(input_id)
                except (KeyError, FileNotFoundError):
                    continue
                if candidate.original_source_path or candidate.input_artifact_ids:
                    next_artifact = candidate
                    break
            if next_artifact is None:
                break
            current = next_artifact

        ordered_suffix = "".join(f"_{item}" for item in reversed(suffixes))
        extension = Path(artifact.path).suffix.lower() or Path(source_name).suffix.lower() or ".png"
        stem = self._safe_file_stem(source_name)
        candidate = f"{stem}{ordered_suffix}{extension}"
        number = 1
        while candidate.casefold() in used_names:
            candidate = f"{stem}{ordered_suffix}-{number}{extension}"
            number += 1
        used_names.add(candidate.casefold())
        return candidate

    @staticmethod
    def _available_destination(destination: Path, reserved: set[Path]) -> Path:
        if not destination.exists() and destination not in reserved:
            return destination
        for number in range(1, 10_000):
            alternate = destination.with_name(f"{destination.stem}-{number}{destination.suffix}")
            if not alternate.exists() and alternate not in reserved:
                return alternate
        raise ExecutionFailure(
            "OUTPUT_NAME_UNAVAILABLE",
            f"No available name remains for {destination.name}.",
        )

    def _save_output(
        self,
        control: _RunControl,
        node: WorkflowNode,
        value: Any,
    ) -> ArtifactRecord | list[ArtifactRecord]:
        artifacts = _artifact_values(value)
        if not artifacts:
            raise ExecutionFailure("MISSING_INPUT", "Save node needs an artifact.")

        grant_id = str(node.parameters.get("destinationGrantId") or "")
        if node.schema_id == "lluna.output.save_video":
            if len(artifacts) != 1:
                raise ExecutionFailure("INVALID_BATCH", "Save Video accepts one video.")
            destination = self._resolve_grant(
                grant_id,
                mode="write",
                empty_message="Choose a destination file for Save Video.",
            )
            source = Path(artifacts[0].path)
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copy2(source, temporary)
            temporary.replace(destination)
            return self._artifacts.register_source(destination, media_type=artifacts[0].media_type)

        directory = self._resolve_grant(
            grant_id,
            mode="directory",
            empty_message="Choose a destination folder for Save Image.",
        )
        policy = str(node.parameters.get("conflictPolicy") or "ask")
        if policy not in {"ask", "replace", "keep-both"}:
            raise ExecutionFailure("INVALID_PARAMETER", "Choose a valid file conflict policy.")

        used_names: set[str] = set()
        targets = [
            directory / self._lineage_file_name(control, item, used_names) for item in artifacts
        ]
        existing = [target for target in targets if target.exists()]
        if existing and policy == "ask":
            preview = ", ".join(item.name for item in existing[:3])
            remainder = len(existing) - 3
            if remainder > 0:
                preview += f" and {remainder} more"
            raise ExecutionFailure(
                "OUTPUT_EXISTS",
                f"{len(existing)} output file(s) already exist: {preview}. Choose Replace existing or Keep both on the Save Image node, then run again.",
            )
        if policy == "keep-both":
            reserved: set[Path] = set()
            targets = [self._available_destination(target, reserved) for target in targets]
            reserved.update(targets)

        saved: list[ArtifactRecord] = []
        item_count = len(artifacts)
        for item_index, (artifact, destination) in enumerate(
            zip(artifacts, targets, strict=True)
        ):
            self._save_item_progress(
                control,
                node,
                item_index=item_index,
                item_count=item_count,
                item_progress=0,
                item_name=destination.name,
                item_status="SAVING",
                detail=f"Saving to {destination.name}",
            )
            temporary = destination.with_suffix(destination.suffix + f".{uuid4().hex}.tmp")
            try:
                source = Path(artifact.path)
                total_bytes = max(source.stat().st_size, 1)
                copied_bytes = 0
                last_progress = 0
                with source.open("rb") as source_file, temporary.open("wb") as target_file:
                    while chunk := source_file.read(1024 * 1024):
                        target_file.write(chunk)
                        copied_bytes += len(chunk)
                        item_progress = min(99, int(copied_bytes * 100 / total_bytes))
                        if item_progress >= last_progress + 5:
                            last_progress = item_progress
                            self._save_item_progress(
                                control,
                                node,
                                item_index=item_index,
                                item_count=item_count,
                                item_progress=item_progress,
                                item_name=destination.name,
                                item_status="SAVING",
                                detail=f"{copied_bytes:,} of {total_bytes:,} bytes copied",
                            )
                shutil.copystat(source, temporary)
                temporary.replace(destination)
            except Exception as exc:
                self._save_item_progress(
                    control,
                    node,
                    item_index=item_index,
                    item_count=item_count,
                    item_progress=0,
                    item_name=destination.name,
                    item_status="FAILED",
                    detail=str(exc),
                )
                raise
            finally:
                temporary.unlink(missing_ok=True)
            saved.append(
                self._artifacts.register_source(destination, media_type=artifact.media_type)
            )
            self._save_item_progress(
                control,
                node,
                item_index=item_index,
                item_count=item_count,
                item_progress=100,
                item_name=destination.name,
                item_status="FINISHED",
                detail=f"Saved as {destination.name}",
            )
        return saved

    def _save_item_progress(
        self,
        control: _RunControl,
        node: WorkflowNode,
        *,
        item_index: int,
        item_count: int,
        item_progress: int,
        item_name: str,
        item_status: str,
        detail: str,
    ) -> None:
        aggregate = int(((item_index + item_progress / 100) / item_count) * 100)
        message = f"{item_status.title()} {item_index + 1} of {item_count}: {item_name}"
        self._node_state(control, node.id, "RUNNING", aggregate, message)
        item = {
            "index": item_index,
            "name": item_name,
            "progress": item_progress,
            "status": item_status,
            "detail": detail,
        }
        with control.lock:
            items = list(control.snapshot.nodes[node.id].save_items)
            while len(items) < item_count:
                pending_index = len(items)
                items.append(
                    {
                        "index": pending_index,
                        "name": f"Image {pending_index + 1}",
                        "progress": 0,
                        "status": "PENDING",
                        "detail": "Waiting to save",
                    }
                )
            items[item_index] = item
            control.snapshot.nodes[node.id].save_items = items
        self._events.publish(
            "node.progress",
            run_id=control.snapshot.run_id,
            node_id=node.id,
            payload={
                "progress": aggregate,
                "message": message,
                "itemIndex": item_index,
                "itemCount": item_count,
                "itemProgress": item_progress,
                "itemName": item_name,
                "itemStatus": item_status,
                "detail": detail,
            },
        )

    def _composite_images(
        self,
        control: _RunControl,
        node: WorkflowNode,
        inputs: dict[str, Any],
        input_artifacts: list[ArtifactRecord],
        cache_key: str,
        *,
        progress_offset: int = 0,
        progress_span: float = 100,
        item_index: int = 0,
        item_count: int = 1,
    ) -> Any:
        foreground = inputs.get("foreground")
        background = inputs.get("background")
        if not isinstance(foreground, ArtifactRecord) or not isinstance(background, ArtifactRecord):
            raise ExecutionFailure(
                "MISSING_INPUT",
                "Composite Background needs foreground and background images.",
            )
        try:
            from PIL import Image, ImageOps

            with Image.open(foreground.path) as source_foreground:
                foreground_image = source_foreground.convert("RGBA")
            with Image.open(background.path) as source_background:
                background_image = source_background.convert("RGBA")
            size = foreground_image.size
            fit = str(node.parameters.get("fit") or "cover")
            if fit == "stretch":
                prepared_background = background_image.resize(
                    size,
                    Image.Resampling.LANCZOS,
                )
            elif fit == "contain":
                prepared_background = Image.new("RGBA", size, (0, 0, 0, 0))
                contained = ImageOps.contain(
                    background_image,
                    size,
                    Image.Resampling.LANCZOS,
                )
                prepared_background.alpha_composite(
                    contained,
                    ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2),
                )
            else:
                prepared_background = ImageOps.fit(
                    background_image,
                    size,
                    Image.Resampling.LANCZOS,
                )
            result = Image.alpha_composite(prepared_background, foreground_image)
            fd, output_raw = tempfile.mkstemp(
                prefix="lluna-composite-",
                suffix=".png",
            )
            os.close(fd)
            result.save(output_raw, format="PNG")
        except (OSError, ValueError) as exc:
            raise ExecutionFailure(
                "COMPOSITE_FAILED",
                f"Could not composite these images: {exc}",
            ) from exc
        artifact = self._artifacts.commit(
            output_raw,
            run_id=control.snapshot.run_id,
            node_id=node.id,
            schema_id=node.schema_id,
            inputs=input_artifacts,
            parameters_hash=cache_key,
        )
        Path(output_raw).unlink(missing_ok=True)
        progress = min(100, int(progress_offset + progress_span))
        self._node_state(
            control,
            node.id,
            "RUNNING",
            progress,
            f"Composited item {item_index + 1} of {item_count}",
        )
        self._events.publish(
            "artifact.created",
            run_id=control.snapshot.run_id,
            node_id=node.id,
            payload={
                "artifactId": artifact.artifact_id,
                "itemIndex": item_index,
                "itemCount": item_count,
            },
        )
        self._events.publish(
            "node.progress",
            run_id=control.snapshot.run_id,
            node_id=node.id,
            payload={
                "progress": progress,
                "itemIndex": item_index,
                "itemCount": item_count,
                "message": f"Composited item {item_index + 1} of {item_count}",
            },
        )
        return artifact

    def _build_control_map(
        self,
        control: _RunControl,
        node: WorkflowNode,
        inputs: dict[str, Any],
        input_artifacts: list[ArtifactRecord],
        cache_key: str,
    ) -> ArtifactRecord:
        """Produce a ControlNet hint image from a source image.

        Runs in-process rather than on the inference worker: Canny is pure
        OpenCV, and holding a GPU slot for it would serialise it behind model
        work for no reason.
        """
        from backend.ai import preprocessors

        source = inputs.get("image")
        if not isinstance(source, ArtifactRecord):
            raise ExecutionFailure("MISSING_INPUT", "Control Map needs a source image.")
        kind = str(node.parameters.get("kind") or "canny")
        try:
            from PIL import Image

            with Image.open(source.path) as opened:
                control_map = preprocessors.run(
                    kind,
                    opened.convert("RGB"),
                    **(
                        {
                            "low": int(node.parameters.get("low", 100)),
                            "high": int(node.parameters.get("high", 200)),
                        }
                        if kind == "canny"
                        else {}
                    ),
                )
            fd, output_raw = tempfile.mkstemp(prefix="lluna-control-", suffix=".png")
            os.close(fd)
            control_map.save(output_raw, format="PNG")
        except preprocessors.PreprocessorError as exc:
            raise ExecutionFailure("CONTROL_MAP_FAILED", str(exc)) from exc
        except (OSError, TypeError, ValueError) as exc:
            raise ExecutionFailure(
                "CONTROL_MAP_FAILED", f"Could not build the control map: {exc}"
            ) from exc
        artifact = self._artifacts.commit(
            output_raw,
            run_id=control.snapshot.run_id,
            node_id=node.id,
            schema_id=node.schema_id,
            inputs=input_artifacts,
            parameters_hash=cache_key,
        )
        Path(output_raw).unlink(missing_ok=True)
        self._node_state(control, node.id, "RUNNING", 100, f"Built a {kind} control map")
        return artifact

    def _apply_image_effects(
        self,
        control: _RunControl,
        node: WorkflowNode,
        inputs: dict[str, Any],
        input_artifacts: list[ArtifactRecord],
        cache_key: str,
        *,
        progress_offset: int = 0,
        progress_span: float = 100,
        item_index: int = 0,
        item_count: int = 1,
    ) -> ArtifactRecord:
        """Apply lightweight, deterministic image effects as a real graph step."""
        source = inputs.get("image")
        if not isinstance(source, ArtifactRecord):
            raise ExecutionFailure("MISSING_INPUT", "Image Effects needs an image.")
        preset = str(node.parameters.get("preset") or "none")
        presets = {
            "none": (1.0, 1.0, 1.0, 1.0, 1.0),
            "vivid": (1.0, 1.08, 1.35, 1.0, 1.0),
            "soft": (1.08, 0.92, 0.82, 1.0, 1.0),
            "warm": (1.0, 1.02, 1.16, 1.05, 0.92),
            "cool": (1.0, 1.05, 0.94, 0.94, 1.06),
            "mono": (1.0, 1.08, 0.0, 1.0, 1.0),
        }
        if preset not in presets:
            raise ExecutionFailure("INVALID_PARAMETER", "Choose a valid image effect.")
        preset_brightness, preset_contrast, preset_color, red_gain, blue_gain = presets[preset]
        try:
            from PIL import Image, ImageEnhance, ImageFilter

            with Image.open(source.path) as opened:
                rgba = opened.convert("RGBA")
            alpha = rgba.getchannel("A")
            image = rgba.convert("RGB")
            if red_gain != 1.0 or blue_gain != 1.0:
                red, green, blue = image.split()
                red = red.point(lambda value: min(255, round(value * red_gain)))
                blue = blue.point(lambda value: min(255, round(value * blue_gain)))
                image = Image.merge("RGB", (red, green, blue))
            brightness = float(node.parameters.get("brightness", 1.0))
            contrast = float(node.parameters.get("contrast", 1.0))
            saturation = float(node.parameters.get("saturation", 1.0))
            blur = float(node.parameters.get("blur", 0.0))
            sharpen = float(node.parameters.get("sharpen", 0.0))
            image = ImageEnhance.Brightness(image).enhance(preset_brightness * brightness)
            image = ImageEnhance.Contrast(image).enhance(preset_contrast * contrast)
            image = ImageEnhance.Color(image).enhance(preset_color * saturation)
            if blur > 0:
                image = image.filter(ImageFilter.GaussianBlur(radius=min(20.0, blur)))
            if sharpen > 0:
                image = image.filter(
                    ImageFilter.UnsharpMask(
                        radius=2,
                        percent=min(500, round(sharpen * 100)),
                        threshold=3,
                    )
                )
            result = image.convert("RGBA")
            result.putalpha(alpha)
            fd, output_raw = tempfile.mkstemp(prefix="lluna-effects-", suffix=".png")
            os.close(fd)
            result.save(output_raw, format="PNG")
        except (OSError, TypeError, ValueError) as exc:
            raise ExecutionFailure(
                "IMAGE_EFFECT_FAILED",
                f"Could not apply the image effect: {exc}",
            ) from exc
        artifact = self._artifacts.commit(
            output_raw,
            run_id=control.snapshot.run_id,
            node_id=node.id,
            schema_id=node.schema_id,
            inputs=input_artifacts,
            parameters_hash=cache_key,
        )
        Path(output_raw).unlink(missing_ok=True)
        progress = min(100, int(progress_offset + progress_span))
        message = f"Applied effect to item {item_index + 1} of {item_count}"
        self._node_state(control, node.id, "RUNNING", progress, message)
        self._events.publish(
            "artifact.created",
            run_id=control.snapshot.run_id,
            node_id=node.id,
            payload={
                "artifactId": artifact.artifact_id,
                "itemIndex": item_index,
                "itemCount": item_count,
            },
        )
        self._events.publish(
            "node.progress",
            run_id=control.snapshot.run_id,
            node_id=node.id,
            payload={
                "progress": progress,
                "itemIndex": item_index,
                "itemCount": item_count,
                "message": message,
            },
        )
        return artifact

    def _run_inference(
        self,
        control: _RunControl,
        node: WorkflowNode,
        inputs: dict[str, Any],
        input_artifacts: list[ArtifactRecord],
        cache_key: str,
        *,
        progress_offset: int = 0,
        progress_span: float = 100,
        item_index: int = 0,
        item_count: int = 1,
        device: str = "",
    ) -> Any:
        # Keep direct payload-construction tests able to exercise this method
        # with a stubbed worker even when CI enables the fake worker globally.
        if os.environ.get("LLUNA_FAKE_WORKER") == "1" and control is not None:
            return self._fake_inference(
                control,
                node,
                input_artifacts,
                cache_key,
                progress_offset=progress_offset,
                progress_span=progress_span,
                item_index=item_index,
                item_count=item_count,
            )
        settings = get_settings()
        adapter = NODE_REGISTRY[node.schema_id].adapter
        job_types = {
            "enhance": JobType.ENHANCE,
            "low_light": JobType.LOW_LIGHT,
            "generate": JobType.GENERATE,
            "lama_retouch": JobType.LAMA_RETOUCH,
            "select_subject": JobType.SELECT_SUBJECT,
            "subtitle": JobType.SUBTITLE,
            "birefnet": JobType.BIREFNET,
            "describe_image": JobType.DESCRIBE_IMAGE,
        }
        job_type = job_types.get(str(adapter))
        if job_type is None:
            raise ExecutionFailure("INTERNAL", f"No adapter for {node.schema_id}")
        output_suffix = (
            ".mov"
            if adapter == "birefnet"
            and "video" in node.schema_id
            and str(node.parameters.get("outputMode", "transparent")) == "transparent"
            else ".mp4"
            if "video" in node.schema_id
            else ".png"
        )
        fd, output_raw = tempfile.mkstemp(prefix="lluna-node-", suffix=output_suffix)
        os.close(fd)
        Path(output_raw).unlink(missing_ok=True)

        def artifact_path(name: str) -> str | None:
            value = inputs.get(name)
            return value.path if isinstance(value, ArtifactRecord) else None

        params = node.parameters
        payload: dict[str, Any] = {
            "hardware_acceleration": settings.runtime.hardware_acceleration,
            "output_path": output_raw,
        }
        if adapter == "enhance":
            model_value = params.get("model") or settings.enhancement.mode
            if model_value in {"SeedVR2_3B", "SeedVR2_7B"}:
                model_parameter = next(
                    item for item in get_node(node.schema_id).parameters if item.id == "model"
                )
                selected_option = next(
                    (item for item in model_parameter.options if item.get("value") == model_value),
                    None,
                )
                selected_model_id = str((selected_option or {}).get("modelId") or "seedvr2-3b")
                job_type = JobType.SEEDVR
                payload.update(
                    input_path=artifact_path("video" if "video" in node.schema_id else "image"),
                    model_id=selected_model_id,
                    target_long_edge=int(params.get("seedvrTargetLongEdge") or 2048),
                    sp_size=int(params.get("seedvrSpSize") or 1),
                    seed=int(params.get("seedvrSeed", 666)),
                )
            elif model_value == "SUPIR":
                llava = inputs.get("llava")
                llava = llava if isinstance(llava, dict) else {}
                job_type = JobType.SUPIR
                preset = str(params.get("supirPreset") or "quality")
                preset_values = {
                    "quality": {
                        "s_cfg": 6.0,
                        "spt_linear_cfg": 3.0,
                        "s_noise": 1.02,
                        "s_stage2": 0.93,
                    },
                    "fidelity": {
                        "s_cfg": 4.0,
                        "spt_linear_cfg": 1.0,
                        "s_noise": 1.01,
                        "s_stage2": 1.0,
                    },
                }.get(preset, {})
                payload.update(
                    input_path=artifact_path("image"),
                    variant=params.get("supirVariant") or "Q",
                    upscale=int(params.get("upscale", 2)),
                    min_size=int(params.get("minSize", 1024)),
                    edm_steps=int(params.get("edmSteps", 50)),
                    s_stage1=float(params.get("sStage1", -1.0)),
                    s_stage2=float(preset_values.get("s_stage2", params.get("sStage2", 1.0))),
                    s_cfg=float(preset_values.get("s_cfg", params.get("sCfg", 4.0))),
                    seed=int(params.get("seed", 1234)),
                    s_churn=float(params.get("sChurn", 5)),
                    s_noise=float(preset_values.get("s_noise", params.get("sNoise", 1.01))),
                    prompt=params.get("prompt") or "",
                    positive_prompt=params.get("positivePrompt") or "",
                    negative_prompt=params.get("negativePrompt") or "",
                    color_fix_type=params.get("colorFixType") or "Wavelet",
                    linear_cfg=bool(params.get("linearCfg", True)),
                    linear_s_stage2=bool(params.get("linearStage2", False)),
                    spt_linear_cfg=float(
                        preset_values.get("spt_linear_cfg", params.get("cfgStart", 1.0))
                    ),
                    spt_linear_s_stage2=float(params.get("stage2Start", 0.0)),
                    gamma_correction=float(params.get("gammaCorrection", 1.0)),
                    diff_dtype=params.get("diffDtype") or "fp16",
                    ae_dtype=params.get("aeDtype") or "bf16",
                    use_llava=bool(params.get("useLlava", True)),
                    llava_temperature=float(
                        llava.get("temperature", params.get("llavaTemperature", 0.2))
                    ),
                    llava_top_p=float(llava.get("topP", params.get("llavaTopP", 0.7))),
                    llava_question=(
                        llava.get("question") or params.get("llavaQuestion") or ""
                    ),
                    load_8bit_llava=bool(
                        llava.get("load8Bit", params.get("load8BitLlava", False))
                    ),
                    loading_half_params=bool(params.get("loadingHalfParams", False)),
                    use_tile_vae=bool(params.get("useTileVae", False)),
                    encoder_tile_size=int(params.get("encoderTileSize", 512)),
                    decoder_tile_size=int(params.get("decoderTileSize", 64)),
                )
            else:
                payload.update(
                    input_path=artifact_path("image"),
                    mode=model_value,
                    denoise=bool(params.get("denoise", settings.enhancement.denoise_enabled)),
                    denoise_strength=params.get("denoiseStrength")
                    or settings.enhancement.denoise_strength,
                    effective_settings={
                        "max_long_edge": int(
                            params.get("maxLongEdge") or settings.enhancement.max_long_edge
                        )
                    },
                )
        elif adapter == "low_light":
            payload.update(
                input_path=artifact_path("image"),
                mode=params.get("model") or settings.low_light.mode,
            )
        elif adapter == "generate":
            model_value = params.get("model") or settings.generation.mode
            model_parameter = next(
                item for item in get_node(node.schema_id).parameters if item.id == "model"
            )
            selected_option = next(
                (item for item in model_parameter.options if item.get("value") == model_value),
                None,
            )
            capabilities = selected_option.get("capabilities", {}) if selected_option else {}
            step_contract = capabilities.get("steps") or {}
            from backend.models.service import generation_minimum_vram_mb

            payload.update(
                prompt=inputs.get("prompt") or params.get("prompt") or "",
                mode=model_value,
                minimum_vram_mb=generation_minimum_vram_mb(str(model_value)),
                dtype=str(params.get("dtype") or "auto"),
                width=int(
                    params.get("width")
                    or (capabilities.get("supportedWidths") or [settings.generation.width])[0]
                ),
                height=int(
                    params.get("height")
                    or (capabilities.get("supportedHeights") or [settings.generation.height])[0]
                ),
                steps=int(
                    params.get("steps") or step_contract.get("default") or settings.generation.steps
                ),
            )
            if node.schema_id == "lluna.generate.image.edit":
                input_path = artifact_path("image")
                if not input_path:
                    raise ExecutionFailure("MISSING_INPUT", "Edit Image needs a source image.")
                payload["input_path"] = input_path
                denoise_strength = params.get("denoiseStrength")
                payload["strength"] = float(
                    denoise_strength if denoise_strength is not None else 0.65
                )
            if capabilities.get("guidance") is True:
                payload["guidance"] = float(
                    params.get(
                        "guidance", (capabilities.get("guidanceScale") or {}).get("default", 1.0)
                    )
                )
            if (
                capabilities.get("negativePrompt") is True
                and str(params.get("negativePrompt") or "").strip()
            ):
                payload["negative_prompt"] = str(params["negativePrompt"]).strip()
            if capabilities.get("seed") is True and int(params.get("seed", -1)) >= 0:
                payload["seed"] = int(params["seed"])
            selected_loras = params.get("loras")
            if selected_loras:
                payload["loras"] = selected_loras
            control_inputs = inputs.get("control")
            if control_inputs:
                controls = (
                    control_inputs if isinstance(control_inputs, (list, tuple)) else [control_inputs]
                )
                payload["controlnets"] = [item for item in controls if isinstance(item, dict)]
        elif adapter == "lama_retouch":
            from backend.models.paths import SubtitleModelPaths, prepare_bundled_subtitle_models

            paths = SubtitleModelPaths.resolve(settings.subtitle)
            prepare_bundled_subtitle_models(paths)
            payload.update(
                image_path=artifact_path("image"),
                mask_path=artifact_path("mask"),
                model_path=str(paths.lama_dir / "big-lama.pt"),
            )
        elif adapter == "select_subject":
            payload.update(
                image_path=artifact_path("image"),
                output_mask_path=output_raw,
                text=params.get("text") or "",
                points=params.get("points") or None,
                labels=params.get("labels") or None,
                confidence_threshold=settings.object_selection.confidence_threshold,
                mask_threshold=settings.object_selection.mask_threshold,
            )
        elif adapter == "subtitle":
            source = artifact_path("video") or artifact_path("image")
            payload.update(
                video_path=source,
                options=_subtitle_options(params),
                config=settings.subtitle.to_payload(),
            )
        elif adapter == "birefnet":
            model_value = str(params.get("model") or "BiRefNet")
            model_parameter = next(
                item for item in get_node(node.schema_id).parameters if item.id == "model"
            )
            selected_option = next(
                (item for item in model_parameter.options if item.get("value") == model_value),
                None,
            )
            model_id = str((selected_option or {}).get("modelId") or "birefnet")
            model_path = None
            if model_id not in {
                "birefnet",
                "birefnet-dynamic",
                "birefnet-hr",
                "birefnet-hr-matting",
                "birefnet-lite-2k",
                "birefnet-matting",
            }:
                try:
                    from backend.models.dynamic_registry import DynamicModelRegistry

                    model_path = str(DynamicModelRegistry.instance().get(model_id).path)
                except (KeyError, OSError, ValueError) as exc:
                    raise ExecutionFailure("MODEL_UNAVAILABLE", f"Custom BiRefNet model is unavailable: {model_id}") from exc
            input_name = "video" if "video" in node.schema_id else "image"
            payload.update(
                input_path=artifact_path(input_name),
                media_type="video" if input_name == "video" else "image",
                model_id=model_id,
                model_path=model_path,
                resolution=int(params.get("resolution") or 1024),
                precision=str(params.get("precision") or "auto"),
                threshold=float(params.get("threshold", 0.5)),
                feather=int(params.get("feather") or 0),
                output_mode=str(params.get("outputMode") or "transparent"),
                background_color=str(params.get("backgroundColor") or "#ffffff"),
            )
        elif adapter == "describe_image":
            payload.update(
                model=str(params.get("model") or ""),
                input_path=artifact_path("image"),
                instruction=str(params.get("instruction") or ""),
                temperature=float(params["temperature"]) if params.get("temperature") is not None else None,
                top_p=float(params["topP"]) if params.get("topP") is not None else None,
                max_new_tokens=int(params["maxNewTokens"]) if params.get("maxNewTokens") is not None else None,
            )
        return self._invoke_worker(
            control,
            node,
            job_type,
            payload,
            output_raw,
            input_artifacts,
            cache_key,
            progress_offset=progress_offset,
            progress_span=progress_span,
            item_index=item_index,
            item_count=item_count,
            device=device,
        )

    def _invoke_worker(
        self,
        control: _RunControl,
        node: WorkflowNode,
        job_type: JobType,
        payload: dict[str, Any],
        output_path: str,
        input_artifacts: list[ArtifactRecord],
        cache_key: str,
        *,
        progress_offset: int = 0,
        progress_span: float = 100,
        item_index: int = 0,
        item_count: int = 1,
        device: str = "",
    ) -> Any:
        from backend.tools.inference.client import InferClient

        run_id = control.snapshot.run_id
        RETRYABLE_CODES = {"TIMEOUT", "WORKER_CRASH", "BUSY"}
        retry_limit = max(0, int(get_settings().runtime.node_retry_limit))

        def log(message: str) -> None:
            self._events.publish(
                "node.log", run_id=run_id, node_id=node.id, payload={"message": str(message)}
            )

        def preview(image: str) -> None:
            self._events.publish(
                "node.preview", run_id=run_id, node_id=node.id, payload={"image": image}
            )

        attempt = 0
        while True:
            done = threading.Event()
            result_path: list[str] = []
            error: list[str] = []

            def progress(value: int) -> None:
                aggregate = min(
                    100,
                    int(progress_offset + progress_span * int(value) / 100),
                )
                self._node_state(
                    control,
                    node.id,
                    "RUNNING",
                    aggregate,
                    f"Processing item {item_index + 1} of {item_count}",
                )
                self._events.publish(
                    "node.progress",
                    run_id=run_id,
                    node_id=node.id,
                    payload={
                        "progress": aggregate,
                        "itemProgress": int(value),
                        "itemIndex": item_index,
                        "itemCount": item_count,
                        "message": f"Processing item {item_index + 1} of {item_count}",
                    },
                )

            def result(path: str) -> None:
                result_path.append(str(path))
                done.set()

            def failed(message: str) -> None:
                error.append(str(message))
                done.set()

            client = InferClient.for_device(device)
            worker_id = client.start_job(
                job_type,
                payload,
                on_progress=progress,
                on_log=log,
                on_result=result,
                on_error=failed,
                on_done=done.set,
                on_preview=preview,
                coalesce=False,
            )
            if worker_id < 0:
                error = ["BUSY"]
            else:
                with control.lock:
                    control.worker_jobs.add((client, worker_id))
                try:
                    while not done.wait(0.2):
                        if control.cancel.is_set():
                            client.cancel(worker_id)
                finally:
                    # Always deregister: leaving a finished job registered would make a
                    # later Stop cancel whatever job inherited that id on this client.
                    with control.lock:
                        control.worker_jobs.discard((client, worker_id))
            if not error:
                final_path = result_path[-1] if result_path else output_path
                break
            code = {
                "__cancelled__": "CANCELLED",
                "TIMEOUT": "TIMEOUT",
                "CRASH": "WORKER_CRASH",
                "BUSY": "BUSY",
            }.get(error[0], "INTERNAL")
            retryable = code in RETRYABLE_CODES
            if retryable and not control.cancel.is_set() and attempt < retry_limit:
                attempt += 1
                log(f"Retrying after {code.lower()} (attempt {attempt}/{retry_limit})…")
                time.sleep(1.0)
                continue
            raise ExecutionFailure(code, error[0], retryable=retryable)
        if node.schema_id == "lluna.input.describe_image":
            # Text result, not media: it's written to output_path as UTF-8
            # by _job_describe_image, so it's read back and returned as a
            # plain port value instead of being committed as an artifact.
            text = Path(final_path).read_text(encoding="utf-8").strip()
            Path(output_path).unlink(missing_ok=True)
            return {NODE_REGISTRY[node.schema_id].outputs[0].id: text}
        artifact = self._artifacts.commit(
            final_path,
            run_id=run_id,
            node_id=node.id,
            schema_id=node.schema_id,
            inputs=input_artifacts,
            parameters_hash=cache_key,
        )
        result: Any = artifact
        if node.schema_id == "lluna.image.remove_background":
            auxiliary: dict[str, ArtifactRecord] = {}
            for port_id, suffix in (("mask", ".mask.png"), ("alpha", ".alpha.png")):
                auxiliary_path = Path(f"{final_path}{suffix}")
                if not auxiliary_path.is_file():
                    continue
                auxiliary[port_id] = self._artifacts.commit(
                    auxiliary_path,
                    run_id=run_id,
                    node_id=node.id,
                    schema_id=node.schema_id,
                    inputs=input_artifacts,
                    media_type="image/png",
                    parameters_hash=cache_key,
                )
                auxiliary_path.unlink(missing_ok=True)
            if auxiliary:
                result = {"image": artifact, **auxiliary}
        Path(output_path).unlink(missing_ok=True)
        self._events.publish(
            "artifact.created",
            run_id=run_id,
            node_id=node.id,
            payload={
                "artifactId": artifact.artifact_id,
                "itemIndex": item_index,
                "itemCount": item_count,
            },
        )
        return result

    def _fake_inference(
        self,
        control: _RunControl,
        node: WorkflowNode,
        inputs: list[ArtifactRecord],
        cache_key: str,
        *,
        progress_offset: int = 0,
        progress_span: float = 100,
        item_index: int = 0,
        item_count: int = 1,
    ) -> ArtifactRecord:
        for progress in (10, 40, 75, 100):
            if control.cancel.is_set():
                raise ExecutionFailure("CANCELLED", "Run cancelled.")
            aggregate = min(
                100,
                int(progress_offset + progress_span * progress / 100),
            )
            self._node_state(
                control,
                node.id,
                "RUNNING",
                aggregate,
                f"Processing item {item_index + 1} of {item_count}",
            )
            self._events.publish(
                "node.progress",
                run_id=control.snapshot.run_id,
                node_id=node.id,
                payload={
                    "progress": aggregate,
                    "itemProgress": progress,
                    "itemIndex": item_index,
                    "itemCount": item_count,
                    "message": f"Processing item {item_index + 1} of {item_count}",
                },
            )
        fd, raw = tempfile.mkstemp(prefix="lluna-fake-", suffix=".png")
        os.close(fd)
        if inputs and Path(inputs[0].path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            shutil.copy2(inputs[0].path, raw)
        else:
            png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+ZtL0WQAAAABJRU5ErkJggg=="
            )
            Path(raw).write_bytes(png)
        artifact = self._artifacts.commit(
            raw,
            run_id=control.snapshot.run_id,
            node_id=node.id,
            schema_id=node.schema_id,
            inputs=inputs,
            parameters_hash=cache_key,
        )
        Path(raw).unlink(missing_ok=True)
        self._events.publish(
            "artifact.created",
            run_id=control.snapshot.run_id,
            node_id=node.id,
            payload={
                "artifactId": artifact.artifact_id,
                "itemIndex": item_index,
                "itemCount": item_count,
            },
        )
        return artifact
