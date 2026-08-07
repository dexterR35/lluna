"""Model catalog, import, authentication, and download queue routes."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_token
from backend.models.service import (
    download_queue_snapshot,
    list_models,
    start_local_import,
    start_model_action,
)
from backend.tools.shared.download_queue import ModelDownloadQueue

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class ModelAnalyzeRequest(BaseModel):
    sourceType: Literal["huggingface", "local-folder", "local-file"]
    value: str = ""
    grantId: str = ""
    revision: str = ""


class ModelImportRequest(BaseModel):
    sourceType: Literal["huggingface", "local-folder", "local-file"]
    manifest: dict[str, Any]
    grantId: str = ""


class HuggingFaceConnectRequest(BaseModel):
    token: str = Field(min_length=8, max_length=4096)


class SupirCheckpointRequest(BaseModel):
    grantId: str
    kind: Literal["Q", "F", "sdxl"]


@router.get("/models")
def models() -> list[dict]:
    return list_models()


@router.post("/models/rescan")
def rescan_models() -> dict:
    from backend.models.dynamic_registry import DynamicModelRegistry

    records = DynamicModelRegistry.instance().scan()
    return {"models": list_models(), "discovered": len(records)}


def _granted_path(request: ModelAnalyzeRequest | ModelImportRequest):
    from backend.artifacts.store import DesktopGrantStore

    if not request.grantId:
        raise ValueError("Choose a local model file or folder.")
    mode = "directory" if request.sourceType == "local-folder" else "read"
    return DesktopGrantStore.instance().resolve(request.grantId, mode=mode)


@router.post("/models/analyze")
def analyze_model(request: ModelAnalyzeRequest) -> dict:
    from backend.models.importer import analyze_huggingface, analyze_local

    try:
        if request.sourceType == "huggingface":
            return analyze_huggingface(request.value, revision=request.revision)
        return analyze_local(_granted_path(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        # Hub errors deliberately become a concise install-analysis error; token
        # values and upstream response bodies are never returned to the renderer.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/models/import", status_code=202)
def import_model(request: ModelImportRequest) -> dict:
    from backend.models.importer import register_huggingface

    try:
        if request.sourceType == "huggingface":
            manifest = register_huggingface(request.manifest)
            queued = start_model_action(manifest.id, "install")
            return {**queued, "modelId": manifest.id, "operation": "install"}
        return start_local_import(_granted_path(request), request.manifest)
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/models/{model_id}/manifest")
def update_model_manifest(model_id: str, manifest: dict[str, Any]) -> dict:
    from backend.models.dynamic_registry import DynamicModelRegistry
    from backend.models.importer import configure_manifest

    try:
        value = configure_manifest(manifest)
        if value.id != model_id:
            raise ValueError("A model id cannot be changed after registration.")
        DynamicModelRegistry.instance().configure(model_id, value)
        return DynamicModelRegistry.instance().get(model_id).to_inventory()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/huggingface/status")
def huggingface_status(verify: bool = False) -> dict:
    from backend.tools.shared.huggingface import hf_auth_status

    try:
        return hf_auth_status(verify=verify)
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail=f"Hugging Face connection failed: {exc}"
        ) from exc


@router.post("/huggingface/connect")
def connect_huggingface(request: HuggingFaceConnectRequest) -> dict:
    from backend.tools.shared.huggingface import save_hf_token, validate_hf_token

    try:
        status = validate_hf_token(request.token)
        save_hf_token(request.token)
        return status
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail=f"The Hugging Face token was rejected: {exc}"
        ) from exc


@router.delete("/huggingface/connect")
def disconnect_huggingface() -> dict:
    from backend.tools.shared.huggingface import clear_hf_token

    clear_hf_token()
    return {"connected": False, "account": "", "role": "", "storage": "none"}


def action(model_id: str, operation: str) -> dict:
    try:
        return {
            **start_model_action(model_id, operation),
            "modelId": model_id,
            "operation": operation,
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown model") from exc


@router.post("/models/{model_id}/install", status_code=202)
def install(model_id: str) -> dict:
    return action(model_id, "install")


@router.post("/models/supir/checkpoint")
def import_supir_checkpoint(request: SupirCheckpointRequest) -> dict:
    from backend.artifacts.store import DesktopGrantStore
    from backend.tools.installers.supir import import_checkpoint, readiness

    try:
        source = DesktopGrantStore.instance().resolve(request.grantId, mode="read")
        destination = import_checkpoint(source, request.kind)
        return {"name": destination.name, "setup": readiness()}
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/models/{model_id}/enable", status_code=202)
def enable(model_id: str) -> dict:
    return action(model_id, "enable")


@router.post("/models/{model_id}/disable", status_code=202)
def disable(model_id: str) -> dict:
    return action(model_id, "disable")


@router.delete("/models/{model_id}", status_code=202)
def remove(model_id: str) -> dict:
    return action(model_id, "remove")


@router.get("/downloads")
def downloads() -> dict:
    return download_queue_snapshot()


@router.post("/downloads/{download_id}/cancel", status_code=202)
def cancel_download(download_id: str) -> dict:
    try:
        job_id = int(download_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid download job ID") from exc
    if not ModelDownloadQueue.instance().stop_job(job_id):
        raise HTTPException(status_code=404, detail="Download job not found")
    return {"downloadId": download_id, "cancelRequested": True}
