"""Shared helpers for queued Settings model install/uninstall."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal, Slot

from backend.tools.model_download_queue import ModelDownloadQueue, WorkFn

OptionalExc = Optional[BaseException]
logger = logging.getLogger(__name__)


class _MainThreadDispatcher(QObject):
    """Deliver Python callbacks to the Qt application thread."""

    invoke_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.invoke_requested.connect(
            self._invoke,
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot(object)
    def _invoke(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            logger.exception("Model install UI completion callback failed")


_dispatcher: Optional[_MainThreadDispatcher] = None
_dispatcher_lock = threading.Lock()
_listener_wrappers: dict[Callable[[], None], Callable[[], None]] = {}


def _main_thread_dispatcher() -> _MainThreadDispatcher:
    """Create the dispatcher while called from the GUI thread."""
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is None:
            app = QCoreApplication.instance()
            if app is None:
                raise RuntimeError(
                    "A Qt application must exist before model jobs are registered."
                )
            _dispatcher = _MainThreadDispatcher()
            _dispatcher.moveToThread(app.thread())
        return _dispatcher


def model_download_queue() -> ModelDownloadQueue:
    return ModelDownloadQueue.instance()


def enqueue_model_job(
    kind: str,
    key: str,
    work_fn: WorkFn,
    on_done: Callable[[OptionalExc], None],
    *,
    operation: str = "install",
) -> int:
    """Run work_fn on the global queue; on_done runs on the Qt main thread."""
    dispatcher = _main_thread_dispatcher()
    queue = model_download_queue()
    if operation == "install" and not queue.is_busy():
        # A previous shutdown can leave an intentional cancel marker for an
        # interrupted job. A new explicit click while idle is a fresh attempt.
        from backend.tools.model_download_registry import ModelDownloadRegistry

        ModelDownloadRegistry.instance().clear_cancel()

    def _main_thread_done(err: OptionalExc) -> None:
        dispatcher.invoke_requested.emit(lambda e=err: on_done(e))

    return queue.enqueue(
        kind,
        key,
        work_fn,
        _main_thread_done,
        operation=operation,
    )


def job_state(kind: str, key: str) -> Optional[str]:
    return model_download_queue().job_state(kind, key)


def queue_position(kind: str, key: str) -> int:
    return model_download_queue().queue_position(kind, key)


def register_queue_listener(listener: Callable[[], None]) -> None:
    dispatcher = _main_thread_dispatcher()
    if listener in _listener_wrappers:
        return

    def _main_thread() -> None:
        dispatcher.invoke_requested.emit(listener)

    _listener_wrappers[listener] = _main_thread
    model_download_queue().add_listener(_main_thread)


def unregister_queue_listener(listener: Callable[[], None]) -> None:
    wrapper = _listener_wrappers.pop(listener, None)
    if wrapper is not None:
        model_download_queue().remove_listener(wrapper)


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
