"""Multiprocess remote callbacks for image-only background removal."""

from __future__ import annotations

import multiprocessing
import threading
from enum import Enum, unique


@unique
class BgRemoveCommand(Enum):
    FINISH = 0
    PROGRESS = 1
    LOG = 2
    ERROR = 3
    PREVIEW_PATH = 4


class BgRemoveRemoteCall:
    """Queue bridge between bg-remove worker process and GUI (same idea as subtitle)."""

    def __init__(self):
        self.queue = multiprocessing.Queue()
        self.callbacks = {}
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            while self.running:
                cmd, args = self.queue.get(block=True)
                if cmd == BgRemoveCommand.FINISH:
                    break
                callback = self.callbacks.get(cmd)
                if callback:
                    callback(*args)
        finally:
            self.running = False

    def stop(self):
        self.running = False
        try:
            self.queue.put((BgRemoveCommand.FINISH, (None,)))
        except Exception:
            pass

    def register_progress(self, callback):
        self.callbacks[BgRemoveCommand.PROGRESS] = callback

    def register_log(self, callback):
        self.callbacks[BgRemoveCommand.LOG] = callback

    def register_error(self, callback):
        self.callbacks[BgRemoveCommand.ERROR] = callback

    def register_preview_path(self, callback):
        self.callbacks[BgRemoveCommand.PREVIEW_PATH] = callback

    @staticmethod
    def put_progress(queue, progress: int):
        queue.put((BgRemoveCommand.PROGRESS, (progress,)))

    @staticmethod
    def put_log(queue, message: str):
        queue.put((BgRemoveCommand.LOG, (message,)))

    @staticmethod
    def put_error(queue, message: str):
        queue.put((BgRemoveCommand.ERROR, (message,)))

    @staticmethod
    def put_preview_path(queue, path: str):
        queue.put((BgRemoveCommand.PREVIEW_PATH, (path,)))

    @staticmethod
    def put_finish(queue):
        queue.put((BgRemoveCommand.FINISH, (None,)))


def bg_remove_worker(queue, input_path: str, output_path: str, mode_value: str, hardware_accel: bool):
    """Child process entry: image-only rembg job.

    Writes to output_path (caller should pass a temp preview path, not the final save).
    """
    try:
        from backend.config import config
        from backend.tools.constant import BgRemoveMode
        from backend.tools.bg_remove import run_bg_remove_job

        config.set(config.hardwareAcceleration, hardware_accel)
        mode = BgRemoveMode(mode_value)

        def on_progress(p: int):
            BgRemoveRemoteCall.put_progress(queue, int(p))

        def on_log(msg: str):
            BgRemoveRemoteCall.put_log(queue, msg)

        run_bg_remove_job(
            input_path,
            output_path,
            mode=mode,
            progress=on_progress,
            log=on_log,
        )
        BgRemoveRemoteCall.put_preview_path(queue, output_path)
        BgRemoveRemoteCall.put_progress(queue, 100)
    except Exception as e:
        import traceback
        traceback.print_exc()
        BgRemoveRemoteCall.put_error(queue, str(e))
    finally:
        BgRemoveRemoteCall.put_finish(queue)
