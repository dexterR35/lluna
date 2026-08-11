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
        payload["backends"] = list(
            dict.fromkeys(
                device["backend"]
                for device in profile.devices()
                if device["backend"] != "unavailable"
            )
        )
        if profile.primary_gpu is not None:
            gpu = profile.primary_gpu
            payload["gpu"] = {
                "name": gpu.model or f"{gpu.vendor} GPU".strip() or "GPU",
                "vramMb": gpu.total_vram_mb,
                "computeCapability": gpu.compute_capability,
            }
    except (ImportError, OSError, RuntimeError):
        pass
    return payload
