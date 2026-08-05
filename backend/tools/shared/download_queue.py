"""Global FIFO queue for Settings model installs (one download at a time)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

JobState = Optional[str]  # None | "active" | "queued"
JobOperation = str  # "install" | "uninstall"
OnDone = Callable[[Optional[BaseException]], None]
WorkFn = Callable[[], None]
Listener = Callable[[], None]
logger = logging.getLogger(__name__)


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
    cancel_event: threading.Event = field(default_factory=threading.Event)
    stop_requested: bool = False
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    downloaded_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    bytes_per_second: Optional[float] = None
    transfer_started_at: Optional[float] = None
    last_sample_at: Optional[float] = None
    last_sample_bytes: Optional[int] = None


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
    downloaded_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    bytes_per_second: Optional[float] = None
    elapsed_seconds: float = 0.0
    eta_seconds: Optional[float] = None


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
                logger.exception("Model download queue listener failed")

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
        from backend.diagnostics import runtime as diag

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
                        state=(
                            "stopping"
                            if self._current.stop_requested
                            else "active"
                        ),
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
        downloaded_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
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
            bytes_changed = self._update_transfer_metrics_unlocked(
                job,
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes,
            )
            changed = progress_changed or detail != job.detail or bytes_changed
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
                from backend.diagnostics import runtime as diag

                diag.progress(
                    f"model:{job.kind}:{job.key}",
                    normalized,
                    f"{job.operation} {job.key}",
                )
            self._notify()

    def stop_job(self, job_id: int) -> bool:
        """Stop an active job or remove a waiting job from the FIFO queue."""
        callback: Optional[OnDone] = None
        err: Optional[BaseException] = None
        stopped_job: Optional[_Job] = None
        with self._lock:
            if self._current is not None and self._current.job_id == int(job_id):
                if self._current.stop_requested:
                    return True
                self._current.stop_requested = True
                self._current.cancel_event.set()
                self._current.detail = "Cancelling and rolling back installation…"
                stopped_job = self._current
            else:
                for index, job in enumerate(self._queue):
                    if job.job_id != int(job_id):
                        continue
                    stopped_job = self._queue.pop(index)
                    stopped_job.stop_requested = True
                    stopped_job.finished_at = time.monotonic()
                    from backend.tools.shared.download_registry import DownloadCancelled

                    err = DownloadCancelled("Download stopped by user")
                    self._history.insert(
                        0,
                        self._snapshot_unlocked(
                            stopped_job,
                            state="cancelled",
                            position=-1,
                            error=str(err),
                        ),
                    )
                    del self._history[20:]
                    callback = stopped_job.on_done
                    break
                else:
                    return False

        if stopped_job is not None:
            from backend.diagnostics import runtime as diag

            diag.warn(
                f"STOP {stopped_job.operation}  "
                f"{stopped_job.kind}:{stopped_job.key}"
            )
        if callback is not None and err is not None:
            self._drop_stopped_pending(stopped_job)
            try:
                callback(err)
            except Exception:
                logger.exception("Stopped model job callback failed")
        self._notify()
        return True

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
        now = job.finished_at or time.monotonic()
        elapsed = (
            max(0.0, now - job.started_at)
            if job.started_at is not None
            else 0.0
        )
        eta: Optional[float] = None
        if (
            state in {"active", "stopping"}
            and job.progress is not None
            and 0 < job.progress < 100
            and elapsed > 0
        ):
            eta = elapsed * (100 - job.progress) / job.progress
        elif (
            state in {"active", "stopping"}
            and job.downloaded_bytes is not None
            and job.total_bytes is not None
            and job.bytes_per_second
            and job.bytes_per_second > 0
        ):
            eta = max(
                0.0,
                (job.total_bytes - job.downloaded_bytes)
                / job.bytes_per_second,
            )
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
            downloaded_bytes=job.downloaded_bytes,
            total_bytes=job.total_bytes,
            bytes_per_second=job.bytes_per_second,
            elapsed_seconds=elapsed,
            eta_seconds=eta,
        )

    @staticmethod
    def _update_transfer_metrics_unlocked(
        job: _Job,
        *,
        downloaded_bytes: Optional[int],
        total_bytes: Optional[int],
    ) -> bool:
        if downloaded_bytes is None and total_bytes is None:
            return False

        downloaded = (
            job.downloaded_bytes
            if downloaded_bytes is None
            else max(0, int(downloaded_bytes))
        )
        total = (
            job.total_bytes
            if total_bytes is None
            else max(0, int(total_bytes))
        )
        if total is not None and total > 0 and downloaded is not None:
            downloaded = min(downloaded, total)

        now = time.monotonic()
        segment_changed = (
            job.total_bytes is not None
            and total is not None
            and total != job.total_bytes
        ) or (
            job.last_sample_bytes is not None
            and downloaded is not None
            and downloaded < job.last_sample_bytes
        )
        if job.transfer_started_at is None or segment_changed:
            job.transfer_started_at = job.started_at or now
            job.last_sample_at = None
            job.last_sample_bytes = None
            job.bytes_per_second = None

        if downloaded is not None:
            if (
                job.last_sample_at is not None
                and job.last_sample_bytes is not None
                and downloaded >= job.last_sample_bytes
            ):
                seconds = now - job.last_sample_at
                if seconds > 0:
                    current_rate = (downloaded - job.last_sample_bytes) / seconds
                    if current_rate > 0:
                        if job.bytes_per_second is None:
                            job.bytes_per_second = current_rate
                        else:
                            job.bytes_per_second = (
                                job.bytes_per_second * 0.7 + current_rate * 0.3
                            )
            elif (
                job.transfer_started_at is not None
                and now > job.transfer_started_at
                and downloaded > 0
            ):
                job.bytes_per_second = downloaded / (
                    now - job.transfer_started_at
                )
            job.last_sample_at = now
            job.last_sample_bytes = downloaded

        changed = (
            downloaded != job.downloaded_bytes
            or total != job.total_bytes
        )
        job.downloaded_bytes = downloaded
        job.total_bytes = total
        return changed

    @staticmethod
    def _drop_stopped_pending(job: Optional[_Job]) -> None:
        if job is None:
            return
        try:
            from backend.tools.shared.download_registry import ModelDownloadRegistry

            ModelDownloadRegistry.instance().fail(
                job.kind,
                job.key,
                keep_pending=False,
            )
        except Exception:
            logger.exception("Could not remove stopped model from pending state")

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
                    job.started_at = time.monotonic()
                    self._current = job
            self._notify()
            if should_exit:
                return

            err: Optional[BaseException] = None
            from backend.diagnostics import runtime as diag

            diag.model(f"START {job.operation}  {job.kind}:{job.key}")
            try:
                from backend.tools.shared.download_registry import (
                    download_cancellation_scope,
                )

                with download_cancellation_scope(job.cancel_event):
                    job.work_fn()
            except BaseException as e:
                err = e

            with self._lock:
                job.finished_at = time.monotonic()
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

            if job.stop_requested and err is not None:
                self._drop_stopped_pending(job)

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
                logger.exception("Model download completion callback failed")
            self._notify()
