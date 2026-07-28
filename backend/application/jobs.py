"""Shared job status representation for GUI and worker adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic


class JobPhase(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    LOADING_MODEL = "loading_model"
    PROCESSING = "processing"
    POSTPROCESSING = "postprocessing"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    task: str
    phase: JobPhase
    progress: int = 0
    model: str = ""
    device: str = ""
    output_path: str = ""
    message: str = ""
    started_at: float = field(default_factory=monotonic)

    def __post_init__(self) -> None:
        if not 0 <= self.progress <= 100:
            raise ValueError("progress must be between 0 and 100")

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, monotonic() - self.started_at)
