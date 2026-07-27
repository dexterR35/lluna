"""Shared helpers for queued Settings model install/uninstall."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QTimer

from backend.tools.model_download_queue import ModelDownloadQueue, OnDone, WorkFn

OptionalExc = Optional[BaseException]


def model_download_queue() -> ModelDownloadQueue:
    return ModelDownloadQueue.instance()


def enqueue_model_job(
    kind: str,
    key: str,
    work_fn: WorkFn,
    on_done: Callable[[OptionalExc], None],
) -> int:
    """Run work_fn on the global queue; on_done runs on the Qt main thread."""

    def _main_thread_done(err: OptionalExc) -> None:
        QTimer.singleShot(0, lambda e=err: on_done(e))

    return model_download_queue().enqueue(kind, key, work_fn, _main_thread_done)


def job_state(kind: str, key: str) -> Optional[str]:
    return model_download_queue().job_state(kind, key)


def queue_position(kind: str, key: str) -> int:
    return model_download_queue().queue_position(kind, key)


def register_queue_listener(listener: Callable[[], None]) -> None:
    def _main_thread() -> None:
        QTimer.singleShot(0, listener)

    model_download_queue().add_listener(_main_thread)


def unregister_queue_listener(listener: Callable[[], None]) -> None:
    model_download_queue().remove_listener(listener)


def install_button_text(
    *,
    kind: str,
    key: str,
    installing_text: str,
    queued_text: str,
    install_text: str,
) -> str:
    state = job_state(kind, key)
    if state == "active":
        return installing_text
    if state == "queued":
        pos = queue_position(kind, key)
        if pos > 1:
            return queued_text.format(pos - 1)
        return queued_text.format(0)
    return install_text
