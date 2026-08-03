"""Per-project autosave recovery snapshots."""

from __future__ import annotations

from pathlib import Path

from backend.core.paths import PATHS
from backend.graph.schema import WorkflowDocument
from backend.projects.repository import WorkflowRepository


class AutosaveStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PATHS.data_dir / "autosave"
        self.root.mkdir(parents=True, exist_ok=True)
        self.repository = WorkflowRepository()

    def save(self, workflow: WorkflowDocument) -> Path:
        return self.repository.save(self.root / f"{workflow.project_id}.midgard.json", workflow)

    def recover(self, project_id: str) -> WorkflowDocument | None:
        path = self.root / f"{project_id}.midgard.json"
        return self.repository.load(path) if path.is_file() else None

    def clear(self, project_id: str) -> None:
        (self.root / f"{project_id}.midgard.json").unlink(missing_ok=True)
