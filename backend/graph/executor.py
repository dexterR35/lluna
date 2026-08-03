"""Workflow execution over the existing single inference-worker boundary."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import threading
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
from backend.graph.cache import build_cache_key
from backend.graph.compiler import compile_workflow
from backend.graph.registry import NODE_REGISTRY
from backend.graph.schema import WorkflowDocument, WorkflowNode
from backend.tools.infer_protocol import JobType


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
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunSnapshot(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)
    run_id: str
    workflow_id: str
    status: RunStatus = RunStatus.QUEUED
    progress: int = 0
    current_node_id: str | None = None
    nodes: dict[str, NodeRun] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ExecutionFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class _RunControl:
    def __init__(
        self,
        snapshot: RunSnapshot,
        workflow: WorkflowDocument,
        *,
        mode: str = "all",
        selected_node_ids: list[str] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.workflow = workflow
        self.mode = mode
        self.selected_node_ids = list(selected_node_ids or [])
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.condition = threading.Condition()
        self.worker_run_id: int | None = None
        self.lock = threading.RLock()


class RunManager:
    _instance: "RunManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._runs: dict[str, _RunControl] = {}
        self._lock = threading.RLock()
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
    ) -> RunSnapshot:
        plan = compile_workflow(workflow, mode=mode, selected_node_ids=selected_node_ids, check_model_availability=True)
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
        snapshot = RunSnapshot(
            run_id=run_id,
            workflow_id=workflow.project_id,
            nodes={step.node_id: NodeRun(node_id=step.node_id) for step in plan.steps},
        )
        control = _RunControl(snapshot, workflow, mode=mode, selected_node_ids=selected_node_ids)
        with self._lock:
            self._runs[run_id] = control
        self._events.publish("run.queued", run_id=run_id, payload={"workflowId": workflow.project_id, "mode": mode})
        threading.Thread(target=self._execute, args=(control,), name=f"workflow-{run_id[:8]}", daemon=True).start()
        return snapshot.model_copy(deep=True)

    def get(self, run_id: str) -> RunSnapshot:
        with self._lock:
            control = self._runs.get(run_id)
        if control is None:
            raise KeyError(run_id)
        with control.lock:
            return control.snapshot.model_copy(deep=True)

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
            control.snapshot.status = RunStatus.CANCEL_REQUESTED
            worker_run_id = control.worker_run_id
        if worker_run_id is not None:
            try:
                from backend.tools.infer_client import InferClient
                InferClient.instance().cancel(worker_run_id)
            except RuntimeError:
                pass
        with control.condition:
            control.condition.notify_all()
        self._events.publish("run.cancel_requested", run_id=run_id)
        return self.get(run_id)

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
            self._save_cache()

    def shutdown(self) -> None:
        with self._lock:
            controls = tuple(self._runs.values())
        for control in controls:
            control.cancel.set()
        try:
            from backend.tools.infer_client import InferClient
            InferClient.instance().shutdown()
        except (ImportError, RuntimeError):
            pass

    def _control(self, run_id: str) -> _RunControl:
        with self._lock:
            control = self._runs.get(run_id)
        if control is None:
            raise KeyError(run_id)
        return control

    def _execute(self, control: _RunControl) -> None:
        snapshot = control.snapshot
        workflow = control.workflow
        plan = compile_workflow(workflow, mode=control.mode, selected_node_ids=control.selected_node_ids, check_model_availability=True)
        nodes = {node.id: node for node in workflow.nodes}
        incoming: dict[str, dict[str, tuple[str, str]]] = {}
        for edge in workflow.edges:
            incoming.setdefault(edge.target_node_id, {})[edge.target_port_id] = (edge.source_node_id, edge.source_port_id)
        active = {step.node_id for step in plan.steps}
        with control.lock:
            snapshot.status = RunStatus.RUNNING
            snapshot.started_at = datetime.now(timezone.utc)
        self._events.publish("run.started", run_id=snapshot.run_id)
        try:
            values = self._boundary_values(workflow, active)
            total = max(len(plan.steps), 1)
            for index, step in enumerate(plan.steps):
                self._wait_if_paused(control)
                if control.cancel.is_set():
                    raise ExecutionFailure("CANCELLED", "Run cancelled.")
                node = nodes[step.node_id]
                definition = NODE_REGISTRY[node.schema_id]
                input_values = {
                    port_id: values[source]
                    for port_id, source in incoming.get(node.id, {}).items()
                    if source in values
                }
                input_artifacts = [value for value in input_values.values() if isinstance(value, ArtifactRecord)]
                cache_key = build_cache_key(node, [item.content_hash for item in input_artifacts])
                cached_id = self._cache.get(cache_key) if definition.cache_policy == "content-addressed" else None
                if cached_id:
                    try:
                        artifact = self._artifacts.get(cached_id)
                        result = artifact
                        self._node_state(control, node.id, "CACHED", 100, "Loaded from cache")
                        with control.lock:
                            control.snapshot.nodes[node.id].artifact_ids = [artifact.artifact_id]
                        self._events.publish("node.cached", run_id=snapshot.run_id, node_id=node.id, payload={"artifactIds": [artifact.artifact_id]})
                    except (KeyError, FileNotFoundError):
                        result = self._run_node(control, node, input_values, input_artifacts, cache_key)
                else:
                    result = self._run_node(control, node, input_values, input_artifacts, cache_key)
                output_ports = definition.outputs
                if isinstance(result, dict) and not isinstance(result, ArtifactRecord):
                    for port_id, value in result.items():
                        values[(node.id, port_id)] = value
                elif output_ports and result is not None:
                    for port in output_ports:
                        values[(node.id, port.id)] = result
                if isinstance(result, ArtifactRecord):
                    with control.lock:
                        snapshot.artifact_ids.append(result.artifact_id)
                    if definition.cache_policy == "content-addressed":
                        with self._cache_lock:
                            self._cache[cache_key] = result.artifact_id
                            self._save_cache()
                with control.lock:
                    snapshot.progress = int((index + 1) * 100 / total)
            with control.lock:
                snapshot.status = RunStatus.COMPLETED
                snapshot.progress = 100
                snapshot.completed_at = datetime.now(timezone.utc)
            self._events.publish("run.completed", run_id=snapshot.run_id, payload={"artifactIds": snapshot.artifact_ids})
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
            self._events.publish("run.cancelled" if cancelled else "run.failed", run_id=snapshot.run_id, node_id=snapshot.current_node_id, payload=snapshot.error or {})
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
                self._events.publish("node.failed", run_id=snapshot.run_id, node_id=snapshot.current_node_id, payload=error)
            self._events.publish("run.failed", run_id=snapshot.run_id, node_id=snapshot.current_node_id, payload=error)

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
                            value = self._artifacts.get(artifact_ids[-1])
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

    def _node_state(self, control: _RunControl, node_id: str, status: str, progress: int, message: str = "") -> None:
        with control.lock:
            state = control.snapshot.nodes[node_id]
            state.status, state.progress, state.message = status, max(0, min(100, progress)), message
            if status == "RUNNING" and state.started_at is None:
                state.started_at = datetime.now(timezone.utc)
            if status in {"SUCCEEDED", "FAILED", "CANCELLED", "CACHED"}:
                state.completed_at = datetime.now(timezone.utc)
            control.snapshot.current_node_id = node_id

    def _run_node(self, control: _RunControl, node: WorkflowNode, inputs: dict[str, Any], input_artifacts: list[ArtifactRecord], cache_key: str) -> Any:
        definition = NODE_REGISTRY[node.schema_id]
        run_id = control.snapshot.run_id
        self._node_state(control, node.id, "RUNNING", 0)
        self._events.publish("node.started", run_id=run_id, node_id=node.id, payload={"schemaId": node.schema_id})
        if definition.adapter in {"load_image", "load_video", "load_mask"}:
            result = self._load_granted_media(node)
        elif definition.adapter == "literal":
            result = {definition.outputs[0].id: node.parameters.get("value")}
        elif definition.adapter == "passthrough":
            result = next(iter(inputs.values()))
        elif definition.adapter == "save":
            result = self._save_output(node, next(iter(inputs.values())))
        else:
            result = self._run_inference(control, node, inputs, input_artifacts, cache_key)
        self._node_state(control, node.id, "SUCCEEDED", 100)
        artifact_ids = [result.artifact_id] if isinstance(result, ArtifactRecord) else []
        with control.lock:
            control.snapshot.nodes[node.id].artifact_ids = artifact_ids
        self._events.publish("node.completed", run_id=run_id, node_id=node.id, payload={"artifactIds": artifact_ids})
        return result

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
        persisted_ids = (node.result or {}).get("artifactIds") or (node.result or {}).get("artifact_ids") or []
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
                raise ExecutionFailure("MISSING_FILE", f"The selected file is missing: {path}") from exc

        if persisted is not None:
            return persisted
        raise ExecutionFailure("MISSING_INPUT", "Choose a local file for this node.")

    def _save_output(self, node: WorkflowNode, value: Any) -> ArtifactRecord:
        if not isinstance(value, ArtifactRecord):
            raise ExecutionFailure("MISSING_INPUT", "Save node needs an artifact.")
        destination = self._resolve_grant(
            str(node.parameters.get("destinationGrantId") or ""),
            mode="write",
            empty_message="Choose a destination file for Save Image.",
        )
        source = Path(value.path)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)
        return self._artifacts.register_source(destination, media_type=value.media_type)

    def _run_inference(self, control: _RunControl, node: WorkflowNode, inputs: dict[str, Any], input_artifacts: list[ArtifactRecord], cache_key: str) -> ArtifactRecord:
        if os.environ.get("MIDGARD_FAKE_WORKER") == "1":
            return self._fake_inference(control, node, input_artifacts, cache_key)
        settings = get_settings()
        adapter = NODE_REGISTRY[node.schema_id].adapter
        job_types = {
            "enhance": JobType.ENHANCE, "low_light": JobType.LOW_LIGHT,
            "generate": JobType.GENERATE, "bg_remove": JobType.BG_REMOVE,
            "lama_retouch": JobType.LAMA_RETOUCH, "select_subject": JobType.SELECT_SUBJECT,
            "subtitle": JobType.SUBTITLE,
        }
        job_type = job_types.get(str(adapter))
        if job_type is None:
            raise ExecutionFailure("INTERNAL", f"No adapter for {node.schema_id}")
        output_suffix = ".mp4" if "video" in node.schema_id else ".png"
        fd, output_raw = tempfile.mkstemp(prefix="midgard-node-", suffix=output_suffix)
        os.close(fd)
        Path(output_raw).unlink(missing_ok=True)
        artifact_path = lambda name: inputs[name].path if isinstance(inputs.get(name), ArtifactRecord) else None
        params = node.parameters
        payload: dict[str, Any] = {"hardware_acceleration": settings.subtitle.hardware_acceleration, "output_path": output_raw}
        if adapter == "enhance":
            payload.update(input_path=artifact_path("image"), mode=params.get("model") or settings.enhancement.mode, denoise=bool(params.get("denoise", settings.enhancement.denoise_enabled)), denoise_strength=params.get("denoiseStrength") or settings.enhancement.denoise_strength, effective_settings={"max_long_edge": int(params.get("maxLongEdge") or settings.enhancement.max_long_edge)})
        elif adapter == "low_light":
            payload.update(input_path=artifact_path("image"), mode=params.get("model") or settings.low_light.mode)
        elif adapter == "generate":
            payload.update(prompt=inputs.get("prompt") or params.get("prompt") or "", mode=params.get("model") or settings.generation.mode, width=int(params.get("width") or settings.generation.width), height=int(params.get("height") or settings.generation.height), steps=int(params.get("steps") or settings.generation.steps))
            if int(params.get("seed", -1)) >= 0:
                payload["seed"] = int(params["seed"])
        elif adapter == "bg_remove":
            payload.update(input_path=artifact_path("image"), mode=params.get("model") or settings.background_removal.mode)
            if artifact_path("protectMask"):
                payload["protect_mask_path"] = artifact_path("protectMask")
        elif adapter == "lama_retouch":
            from backend.models.paths import SubtitleModelPaths, prepare_bundled_subtitle_models
            paths = SubtitleModelPaths.resolve(settings.subtitle)
            prepare_bundled_subtitle_models(paths)
            payload.update(image_path=artifact_path("image"), mask_path=artifact_path("mask"), model_path=str(paths.lama_dir / "big-lama.pt"))
        elif adapter == "select_subject":
            payload.update(image_path=artifact_path("image"), output_mask_path=output_raw, text=params.get("text") or "", points=params.get("points") or None, labels=params.get("labels") or None, more_complex=bool(params.get("moreComplex", settings.object_selection.more_complex)))
        elif adapter == "subtitle":
            source = artifact_path("video") or artifact_path("image")
            payload.update(video_path=source, options=params.get("options") or {}, config=settings.subtitle.to_payload())
        return self._invoke_worker(control, node, job_type, payload, output_raw, input_artifacts, cache_key)

    def _invoke_worker(self, control: _RunControl, node: WorkflowNode, job_type: JobType, payload: dict[str, Any], output_path: str, input_artifacts: list[ArtifactRecord], cache_key: str) -> ArtifactRecord:
        from backend.tools.infer_client import InferClient
        done = threading.Event()
        result_path: list[str] = []
        error: list[str] = []
        run_id = control.snapshot.run_id
        def progress(value: int) -> None:
            self._node_state(control, node.id, "RUNNING", int(value))
            self._events.publish("node.progress", run_id=run_id, node_id=node.id, payload={"progress": int(value)})
        def log(message: str) -> None:
            self._events.publish("node.log", run_id=run_id, node_id=node.id, payload={"message": str(message)})
        def result(path: str) -> None:
            result_path.append(str(path)); done.set()
        def failed(message: str) -> None:
            error.append(str(message)); done.set()
        worker_id = InferClient.instance().start_job(job_type, payload, on_progress=progress, on_log=log, on_result=result, on_error=failed, on_done=done.set, coalesce=False)
        if worker_id < 0:
            raise ExecutionFailure("BUSY", "Another GPU-heavy job is running.", retryable=True)
        with control.lock:
            control.worker_run_id = worker_id
        while not done.wait(0.2):
            if control.cancel.is_set():
                InferClient.instance().cancel(worker_id)
        with control.lock:
            control.worker_run_id = None
        if error:
            code = {"__cancelled__": "CANCELLED", "TIMEOUT": "TIMEOUT", "CRASH": "WORKER_CRASH", "BUSY": "BUSY"}.get(error[0], "INTERNAL")
            raise ExecutionFailure(code, error[0], retryable=code in {"TIMEOUT", "WORKER_CRASH", "BUSY"})
        final_path = result_path[-1] if result_path else output_path
        artifact = self._artifacts.commit(final_path, run_id=run_id, node_id=node.id, inputs=input_artifacts, parameters_hash=cache_key)
        Path(output_path).unlink(missing_ok=True)
        self._events.publish("artifact.created", run_id=run_id, node_id=node.id, payload={"artifactId": artifact.artifact_id})
        return artifact

    def _fake_inference(self, control: _RunControl, node: WorkflowNode, inputs: list[ArtifactRecord], cache_key: str) -> ArtifactRecord:
        for progress in (10, 40, 75, 100):
            if control.cancel.is_set():
                raise ExecutionFailure("CANCELLED", "Run cancelled.")
            self._node_state(control, node.id, "RUNNING", progress)
            self._events.publish("node.progress", run_id=control.snapshot.run_id, node_id=node.id, payload={"progress": progress})
        fd, raw = tempfile.mkstemp(prefix="midgard-fake-", suffix=".png")
        os.close(fd)
        if inputs and Path(inputs[0].path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            shutil.copy2(inputs[0].path, raw)
        else:
            png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+ZtL0WQAAAABJRU5ErkJggg==")
            Path(raw).write_bytes(png)
        artifact = self._artifacts.commit(raw, run_id=control.snapshot.run_id, node_id=node.id, inputs=inputs, parameters_hash=cache_key)
        Path(raw).unlink(missing_ok=True)
        self._events.publish("artifact.created", run_id=control.snapshot.run_id, node_id=node.id, payload={"artifactId": artifact.artifact_id})
        return artifact
