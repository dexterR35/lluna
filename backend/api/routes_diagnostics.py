"""Diagnostics and resource-release routes."""

import platform

from fastapi import APIRouter, Depends

from backend.api.auth import require_token
from backend.core.build_info import VERSION

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/diagnostics")
def diagnostics() -> dict:
    worker = {"alive": False, "active": None}
    try:
        from backend.tools.infer_client import InferClient

        worker = InferClient.instance().status_snapshot()
    except (ImportError, RuntimeError):
        pass
    return {
        "version": VERSION,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "worker": worker,
    }


@router.post("/system/release-models")
def release_models() -> dict:
    try:
        from backend.tools.infer_client import InferClient

        InferClient.instance().release()
    except (ImportError, RuntimeError):
        pass
    return {"released": True}
