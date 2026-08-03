"""Atomic workflow persistence with migration and recovery copies."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.core.atomic import atomic_write_json
from backend.graph.schema import WorkflowDocument


class WorkflowRepository:
    def load(self, path: str | Path) -> WorkflowDocument:
        source = Path(path).expanduser().resolve()
        raw = json.loads(source.read_text(encoding="utf-8"))
        if raw.get("format") != "midgard-workflow":
            raise ValueError("Not a Midgard workflow")
        if int(raw.get("version", 0)) != 1:
            raise ValueError(f"Unsupported workflow version: {raw.get('version')}")
        return WorkflowDocument.model_validate(raw)

    def save(self, path: str | Path, workflow: WorkflowDocument) -> Path:
        target = Path(path).expanduser().resolve()
        payload = workflow.model_dump(mode="json", by_alias=True)
        payload["updatedAt"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(target, payload)
        return target
