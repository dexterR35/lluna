"""Artifact metadata contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    media_type: str
    path: str
    original_source_path: str | None = None
    content_hash: str
    byte_size: int
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    frame_count: int | None = None
    timebase: str | None = None
    streams: list[dict[str, Any]] = Field(default_factory=list)
    alpha: bool | None = None
    color_metadata: dict[str, Any] = Field(default_factory=dict)
    creating_run_id: str | None = None
    creating_node_id: str | None = None
    input_artifact_ids: list[str] = Field(default_factory=list)
    model_revision: str = ""
    parameters_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
