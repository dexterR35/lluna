"""Structured progress and cancellation primitives."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from backend.application.jobs import JobPhase
from backend.diagnostics.errors import CancellationError


@dataclass(frozen=True)
class ProgressEvent:
    phase: JobPhase
    phase_progress: int
    overall_progress: int
    message: str = ""


class CancellationEvent(Protocol):
    def set(self) -> None: ...

    def is_set(self) -> bool: ...


class CancellationToken:
    def __init__(self, event: CancellationEvent | None = None) -> None:
        self._event = event or threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancellationError("The operation was cancelled.")
