"""Artifact media and desktop path-grant routes."""

import shutil
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


class SaveArtifactRequest(BaseModel):
    destinationGrantId: str


@router.post("/desktop/grants")
def issue_grant(request: GrantRequest) -> dict:
    try:
        grant = DesktopGrantStore.instance().issue(request.path, mode=request.mode)
        source = ArtifactStore.instance().register_source(grant.path) if grant.mode == "read" else None
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = {"grantId": grant.grant_id, "name": grant.display_name, "mode": grant.mode}
    if source is not None:
        response.update(
            artifactId=source.artifact_id,
            mediaType=source.media_type,
            width=source.width,
            height=source.height,
            byteSize=source.byte_size,
            alpha=source.alpha,
        )
    return response


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


@router.post("/artifacts/{artifact_id}/save")
def save_artifact(artifact_id: str, request: SaveArtifactRequest) -> dict:
    """Copy a completed artifact to an explicitly granted desktop destination."""
    record = artifact(artifact_id)
    try:
        destination = DesktopGrantStore.instance().resolve(request.destinationGrantId, mode="write")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="The save destination expired. Choose it again.") from exc
    source = Path(record.path)
    try:
        if source != destination:
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copy2(source, temporary)
            temporary.replace(destination)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Could not save artifact: {exc}") from exc
    return {"saved": True, "artifactId": artifact_id, "name": destination.name}
