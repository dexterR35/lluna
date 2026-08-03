"""Model catalog and download queue routes."""

from fastapi import APIRouter, Depends, HTTPException, Response

from backend.api.auth import require_token
from backend.models.service import list_models, start_model_action
from backend.tools.model_download_registry import ModelDownloadRegistry

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/models")
def models() -> list[dict]:
    return list_models()


def action(model_id: str, operation: str) -> dict:
    try:
        return {"actionId": start_model_action(model_id, operation), "modelId": model_id, "operation": operation}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown model") from exc


@router.post("/models/{model_id}/install", status_code=202)
def install(model_id: str) -> dict:
    return action(model_id, "install")


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
    registry = ModelDownloadRegistry.instance()
    return {
        "active": [{"kind": item.kind, "key": item.key} for item in registry.list_active()],
        "pending": [{"kind": item.kind, "key": item.key} for item in registry.list_pending()],
    }


@router.post("/downloads/{download_id}/cancel", status_code=202)
def cancel_download(download_id: str) -> dict:
    ModelDownloadRegistry.instance().request_cancel()
    return {"downloadId": download_id, "cancelRequested": True}
