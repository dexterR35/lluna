"""Shared Select Object infer job for Protect / Retouch dialogs."""

from __future__ import annotations

import os
import traceback
from typing import Callable, Optional

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal

from backend.config import config, tr
from backend.tools import diag
from backend.tools.infer_client import InferClient
from backend.tools.infer_protocol import JobType
from backend.tools.select_object_models import (
    is_active_pair_ready,
)


class SelectObjectController(QObject):
    """Runs SELECT_SUBJECT on demand; emits mask or error."""

    finished = Signal(object)  # np.ndarray uint8 L or None
    failed = Signal(str)
    busy_changed = Signal(bool)
    status = Signal(str)
    progress = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._temps: tuple[str, ...] = ()
        self._image_path = ""

    @property
    def is_busy(self) -> bool:
        return self._busy

    def missing_models_message(self) -> str | None:
        if is_active_pair_ready():
            return None
        return tr["SelectObject"].get(
            "MissingDefaults",
            "Select Object models are not installed. Open Settings → Select Object Models.",
        )

    def run(
        self,
        rgba: Image.Image,
        *,
        click_xy: tuple[int, int] | None = None,
        text: str = "",
    ) -> None:
        if self._busy:
            return
        msg = self.missing_models_message()
        if msg:
            self.failed.emit(msg)
            return

        phrase = (text or "").strip()
        if click_xy is None and not phrase:
            self.failed.emit(tr["SelectObject"].get("NeedClickOrText", "Click the object or enter a name."))
            return

        self._set_busy(True)
        self.status.emit(tr["SelectObject"].get("Running", "Selecting object…"))
        self.progress.emit(5)

        client = InferClient.instance()
        img_path = client.make_temp_path("select_img_", ".png")
        out_path = client.make_temp_path("select_mask_", ".png")
        self._temps = (img_path, out_path)
        self._image_path = img_path
        rgba.convert("RGBA").save(img_path, format="PNG")

        payload = {
            "image_path": img_path,
            "output_mask_path": out_path,
            "hardware_acceleration": bool(config.hardwareAcceleration.value),
            "more_complex": bool(config.selectObjectMoreComplex.value),
        }
        if click_xy is not None:
            payload["points"] = [[int(click_xy[0]), int(click_xy[1])]]
            payload["labels"] = [1]
        if phrase:
            payload["text"] = phrase

        diag.run(
            f"Select Object START  click={'yes' if click_xy else 'no'}  "
            f"text={phrase or '-'}"
        )

        def on_progress(p: int):
            self.progress.emit(int(p))

        def on_log(msg: str):
            diag.worker(f"SelectObject  {msg}")
            lower = msg.lower()
            if "load" in lower:
                self.status.emit(tr["SelectObject"].get("Loading", "Loading models…"))
            else:
                self.status.emit(tr["SelectObject"].get("Running", "Selecting object…"))

        def on_result(result_path: str):
            mask_arr = None
            err = None
            try:
                mask_arr = np.asarray(Image.open(result_path).convert("L"))
            except Exception as e:
                traceback.print_exc()
                err = str(e)
            self._cleanup_temps()
            if err:
                self._finish(None, err)
            else:
                self._finish(mask_arr, None)

        def on_error(msg: str):
            self._cleanup_temps()
            if msg == "BUSY":
                from ui.gpu_busy import gpu_busy_message

                self._finish(None, gpu_busy_message())
            elif msg in ("__cancelled__", "TIMEOUT", "CRASH"):
                self._finish(None, tr["SelectObject"].get("Cancelled", "Select Object cancelled."))
            else:
                self._finish(None, msg)

        client.start_job(
            JobType.SELECT_SUBJECT,
            payload,
            on_progress=on_progress,
            on_log=on_log,
            on_result=on_result,
            on_error=on_error,
            coalesce=False,
        )

    def cancel(self) -> None:
        if not self._busy:
            return
        try:
            InferClient.instance().cancel()
        except Exception:
            traceback.print_exc()

    def _cleanup_temps(self) -> None:
        for p in self._temps:
            InferClient.unlink_quiet(p)
        self._temps = ()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)

    def _finish(self, mask: np.ndarray | None, err: str | None) -> None:
        self._set_busy(False)
        if err:
            diag.error(f"Select Object FAILED  {err}")
            self.failed.emit(err)
            return
        if mask is None or not np.any(mask):
            self.failed.emit(tr["SelectObject"].get("EmptyMask", "No object mask was produced."))
            return
        diag.run("Select Object DONE")
        self.finished.emit(mask)
