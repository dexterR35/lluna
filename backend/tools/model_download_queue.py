"""Global FIFO queue for Settings model installs (one download at a time)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

JobState = Optional[str]  # None | "active" | "queued"
OnDone = Callable[[Optional[BaseException]], None]
WorkFn = Callable[[], None]
Listener = Callable[[], None]


@dataclass
class _Job:
    kind: str
    key: str
    work_fn: WorkFn
    on_done: OnDone


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
    ) -> int:
        """Add a job. Returns 0 if it runs next, else wait position behind active job."""
        with self._lock:
            for job in (*([self._current] if self._current else []), *self._queue):
                if job.kind == kind and job.key == key:
                    return self._position_unlocked(kind, key)

            job = _Job(kind=kind, key=str(key), work_fn=work_fn, on_done=on_done)
            self._queue.append(job)
            pos = self._position_unlocked(kind, key)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._worker_loop, daemon=True)
                self._worker.start()
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
            try:
                job.work_fn()
            except BaseException as e:
                err = e

            with self._lock:
                self._current = None

            try:
                job.on_done(err)
            except Exception:
                pass
            self._notify()
