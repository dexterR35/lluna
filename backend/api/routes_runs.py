"""Workflow run lifecycle routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.api.auth import require_token
from backend.graph.executor import ExecutionFailure, RunManager
from backend.graph.schema import WorkflowDocument

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class StartRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    workflow: WorkflowDocument
    mode: str = "all"
    selected_node_ids: list[str] = Field(default_factory=list, alias="selectedNodeIds")
    force: bool = False
    queue_front: bool = Field(default=False, alias="queueFront")


def dump(snapshot) -> dict:
    return snapshot.model_dump(mode="json", by_alias=True)


@router.post("/runs")
def start_run(request: StartRunRequest) -> dict:
    try:
        return dump(
            RunManager.instance().start(
                request.workflow,
                mode=request.mode,
                selected_node_ids=request.selected_node_ids,
                force=request.force,
                queue_front=request.queue_front,
            )
        )
    except ExecutionFailure as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return dump(RunManager.instance().get(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown run") from exc


@router.get("/queue")
def get_queue() -> dict:
    snapshot = RunManager.instance().queue_snapshot()
    return {
        "running": dump(snapshot["running"]) if snapshot["running"] else None,
        "pending": [dump(item) for item in snapshot["pending"]],
    }


@router.get("/history")
def get_history(limit: int = 100) -> dict:
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    return {"runs": [dump(item) for item in RunManager.instance().history(limit=limit)]}


@router.post("/runs/{run_id}/pause")
def pause(run_id: str) -> dict:
    try:
        return dump(RunManager.instance().pause(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown run") from exc


@router.post("/runs/{run_id}/resume")
def resume(run_id: str) -> dict:
    try:
        return dump(RunManager.instance().resume(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown run") from exc


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str) -> dict:
    try:
        return dump(RunManager.instance().cancel(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown run") from exc


@router.post("/runs/{run_id}/clear-cache")
def clear_cache(run_id: str) -> dict:
    RunManager.instance().clear_cache()
    return {"cleared": True, "runId": run_id}


@router.post("/nodes/{node_id}/preview")
def preview_node(node_id: str, workflow: WorkflowDocument) -> dict:
    return {
        "nodeId": node_id,
        "run": dump(
            RunManager.instance().start(workflow, mode="selected", selected_node_ids=[node_id])
        ),
    }
