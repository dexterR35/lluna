"""Artifact media and desktop path-grant routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.api.auth import require_token
from backend.artifacts.store import ArtifactStore, DesktopGrantStore

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class GrantRequest(BaseModel):
    path: str
    mode: str = "read"


@router.post("/desktop/grants")
def issue_grant(request: GrantRequest) -> dict:
    try:
        grant = DesktopGrantStore.instance().issue(request.path, mode=request.mode)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"grantId": grant.grant_id, "name": grant.display_name, "mode": grant.mode}


def artifact(artifact_id: str):
    try:
        return ArtifactStore.instance().get(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown artifact") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail="Artifact file is missing") from exc


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str):
    record = artifact(artifact_id)
    return FileResponse(record.path, media_type=record.media_type, filename=Path(record.path).name)


@router.get("/artifacts/{artifact_id}/metadata")
def get_artifact_metadata(artifact_id: str) -> dict:
    return artifact(artifact_id).model_dump(mode="json")


@router.get("/artifacts/{artifact_id}/thumbnail")
def get_thumbnail(artifact_id: str):
    record = artifact(artifact_id)
    return FileResponse(record.path, media_type=record.media_type)
