"""Health, readiness, version, and capability routes."""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends

from backend.api.auth import require_token
from backend.core.build_info import VERSION

router = APIRouter()
_ready = False


def set_ready(value: bool) -> None:
    global _ready
    _ready = value


@router.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@router.get("/ready")
def ready() -> dict:
    return {"ready": _ready}


@router.get("/api/version", dependencies=[Depends(require_token)])
def version() -> dict:
    return {"version": VERSION, "python": platform.python_version(), "apiVersion": 1}


@router.get("/api/capabilities", dependencies=[Depends(require_token)])
def capabilities() -> dict:
    payload = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "backends": ["cpu"],
        "gpu": None,
    }
    try:
        from backend.hardware.detector import get_hardware_profile

        profile = get_hardware_profile()
        payload["backends"] = (
            list(profile.available_backends) if hasattr(profile, "available_backends") else ["cpu"]
        )
        if profile.primary_gpu is not None:
            payload["gpu"] = {
                "name": profile.primary_gpu.name,
                "vramMb": profile.primary_gpu.total_vram_mb,
                "computeCapability": profile.primary_gpu.compute_capability,
            }
    except (ImportError, OSError, RuntimeError):
        pass
    return payload
