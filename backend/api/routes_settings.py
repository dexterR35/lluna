"""Typed settings routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_token
from backend.api.events import EventBroker
from backend.configuration.service import ConfigurationService

router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_token)])


@router.get("")
def get_settings() -> dict:
    return ConfigurationService.instance().get().to_dict()


@router.get("/schema")
def settings_schema() -> dict:
    return {
        "schemaVersion": 2,
        "sections": [
            "subtitle",
            "runtime",
            "background_removal",
            "enhancement",
            "low_light",
            "generation",
            "object_selection",
            "save_directory",
        ],
    }


@router.put("")
def put_settings(patch: dict[str, Any]) -> dict:
    try:
        value = ConfigurationService.instance().update(patch)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    EventBroker.instance().publish("settings.changed", payload={"settings": value.to_dict()})
    return value.to_dict()


@router.post("/reset/{section}")
def reset_settings(section: str) -> dict:
    try:
        value = ConfigurationService.instance().reset_section(section)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    EventBroker.instance().publish("settings.changed", payload={"section": section})
    return value.to_dict()
