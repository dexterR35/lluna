"""Global FIFO queue for Settings model installs (one download at a time)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

JobState = Optional[str]  # None | "active" | "queued"
JobOperation = str  # "install" | "uninstall"
OnDone = Callable[[Optional[BaseException]], None]
WorkFn = Callable[[], None]
Listener = Callable[[], None]


@dataclass
class _Job:
    job_id: int
    kind: str
    key: str
    operation: JobOperation
    work_fn: WorkFn
    on_done: OnDone
    progress: Optional[int] = None
    detail: str = ""
    last_progress_notification: float = 0.0
    last_notified_progress: Optional[int] = None


@dataclass(frozen=True)
class DownloadJobSnapshot:
    """Thread-safe, presentation-ready view of one queue or history item."""

    job_id: int
    kind: str
    key: str
    operation: JobOperation
    state: str
    position: int
    progress: Optional[int] = None
    detail: str = ""
    error: str = ""


class ModelDownloadQueue:
    """Process-wide singleton: serializes model install/uninstall jobs."""

    _instance: Optional["ModelDownloadQueue"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: List[_Job] = []
        self._current: Optional[_Job] = None
        self._worker: Optional[threading.Thread] = None
        self._listeners: List[Listener] = []
        self._history: List[DownloadJobSnapshot] = []
        self._next_job_id = 1

    @classmethod
    def instance(cls) -> "ModelDownloadQueue":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def add_listener(self, listener: Listener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Listener) -> None:
        with self._lock:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb()
            except Exception:
                pass

    def enqueue(
        self,
        kind: str,
        key: str,
        work_fn: WorkFn,
        on_done: OnDone,
        *,
        operation: JobOperation = "install",
    ) -> int:
        """Add a job. Returns 0 if it runs next, else wait position behind active job."""
        with self._lock:
            for job in (*([self._current] if self._current else []), *self._queue):
                if job.kind == kind and job.key == key:
                    return self._position_unlocked(kind, key)

            job = _Job(
                job_id=self._next_job_id,
                kind=kind,
                key=str(key),
                operation=str(operation),
                work_fn=work_fn,
                on_done=on_done,
            )
            self._next_job_id += 1
            self._queue.append(job)
            pos = self._position_unlocked(kind, key)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._worker_loop, daemon=True)
                self._worker.start()
        from backend.tools import diag

        diag.model(
            f"QUEUE {job.operation}  {job.kind}:{job.key}  position={pos}"
        )
        self._notify()
        return pos

    def job_state(self, kind: str, key: str) -> JobState:
        with self._lock:
            return self._state_unlocked(kind, str(key))

    def queue_position(self, kind: str, key: str) -> int:
        """0 = active now; 1+ = jobs ahead; -1 = not in queue."""
        with self._lock:
            pos = self._position_unlocked(kind, str(key))
            return pos if pos >= 0 else -1

    def is_busy(self) -> bool:
        with self._lock:
            return self._current is not None or bool(self._queue)

    def current_job(self) -> Optional[tuple[str, str]]:
        with self._lock:
            if self._current is None:
                return None
            return (self._current.kind, self._current.key)

    def pending_count(self) -> int:
        with self._lock:
            n = len(self._queue)
            return n + (1 if self._current else 0)

    def jobs(self, *, include_finished: bool = True) -> List[DownloadJobSnapshot]:
        """Return active, queued, then newest finished jobs."""
        with self._lock:
            snapshots: List[DownloadJobSnapshot] = []
            if self._current is not None:
                snapshots.append(
                    self._snapshot_unlocked(
                        self._current,
                        state="active",
                        position=0,
                    )
                )
            ahead = 1 if self._current is not None else 0
            for job in self._queue:
                snapshots.append(
                    self._snapshot_unlocked(
                        job,
                        state="queued",
                        position=ahead,
                    )
                )
                ahead += 1
            if include_finished:
                snapshots.extend(self._history)
            return snapshots

    def report_current_progress(
        self,
        percent: Optional[int],
        *,
        detail: str = "",
    ) -> None:
        """Update the active job from a download worker and notify the UI."""
        should_notify = False
        with self._lock:
            job = self._current
            if job is None:
                return
            normalized = (
                None if percent is None else max(0, min(100, int(percent)))
            )
            progress_changed = normalized != job.progress
            changed = progress_changed or detail != job.detail
            if not changed:
                return
            job.progress = normalized
            job.detail = str(detail or "")
            now = time.monotonic()
            progress_due = (
                progress_changed and normalized != job.last_notified_progress
            )
            detail_due = (
                normalized in (0, 100)
                or now - job.last_progress_notification >= 0.1
            )
            if progress_due or detail_due:
                job.last_progress_notification = now
                job.last_notified_progress = normalized
                should_notify = True
        if should_notify:
            if normalized is not None:
                from backend.tools import diag

                diag.progress(
                    f"model:{job.kind}:{job.key}",
                    normalized,
                    f"{job.operation} {job.key}",
                )
            self._notify()

    def clear_finished(self) -> None:
        with self._lock:
            if not self._history:
                return
            self._history.clear()
        self._notify()

    def _state_unlocked(self, kind: str, key: str) -> JobState:
        if self._current and self._current.kind == kind and self._current.key == key:
            return "active"
        for job in self._queue:
            if job.kind == kind and job.key == key:
                return "queued"
        return None

    def _position_unlocked(self, kind: str, key: str) -> int:
        if self._current and self._current.kind == kind and self._current.key == key:
            return 0
        ahead = 1 if self._current else 0
        for job in self._queue:
            if job.kind == kind and job.key == key:
                return ahead
            ahead += 1
        return -1

    @staticmethod
    def _snapshot_unlocked(
        job: _Job,
        *,
        state: str,
        position: int,
        error: str = "",
    ) -> DownloadJobSnapshot:
        return DownloadJobSnapshot(
            job_id=job.job_id,
            kind=job.kind,
            key=job.key,
            operation=job.operation,
            state=state,
            position=position,
            progress=job.progress,
            detail=job.detail,
            error=error,
        )

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    self._current = None
                    self._worker = None
                    should_exit = True
                else:
                    should_exit = False
                    job = self._queue.pop(0)
                    self._current = job
            self._notify()
            if should_exit:
                return

            err: Optional[BaseException] = None
            from backend.tools import diag

            diag.model(f"START {job.operation}  {job.kind}:{job.key}")
            try:
                job.work_fn()
            except BaseException as e:
                err = e

            with self._lock:
                self._current = None
                if err is None:
                    job.progress = 100
                    state = "completed"
                    error = ""
                elif type(err).__name__ == "DownloadCancelled":
                    state = "cancelled"
                    error = str(err)
                else:
                    state = "failed"
                    error = str(err)
                self._history.insert(
                    0,
                    self._snapshot_unlocked(
                        job,
                        state=state,
                        position=-1,
                        error=error,
                    ),
                )
                del self._history[20:]

            if err is None:
                diag.model(f"DONE {job.operation}  {job.kind}:{job.key}")
            elif type(err).__name__ == "DownloadCancelled":
                diag.warn(
                    f"CANCELLED {job.operation}  {job.kind}:{job.key}"
                )
            else:
                diag.error(
                    f"FAILED {job.operation}  {job.kind}:{job.key}  "
                    f"{type(err).__name__}: {err}"
                )

            try:
                job.on_done(err)
            except Exception:
                pass
            self._notify()
