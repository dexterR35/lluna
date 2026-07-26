"""Enhance preview dialog after Remove BG - Real-ESRGAN 2×/4×, Apply or Cancel."""

from __future__ import annotations

import threading
import traceback

from PIL import Image
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from qfluentwidgets import BodyLabel, ProgressBar, StrongBodyLabel

from backend.config import config, tr
from backend.tools.constant import EnhanceMode
from backend.tools.enhance_models import (
    apply_default_enhance_model,
    selectable_modes,
)
from ui.component.preview.before_after_preview import BeforeAfterPreview
from ui.component.controls.button_styles import ClickThrottle, make_button
from ui.component.controls.inputs import AppCombo, refresh_combo
from ui.theme import BG, TEXT, DIALOG


class BgEnhanceDialog(QDialog):
    """
    Preview Real-ESRGAN upscale. Run starts the model; Apply commits; Cancel discards.
    Only one enhance job runs at a time; Cancel aborts the queue and frees memory.
    """

    finished_image = Signal(object)  # PIL RGBA
    _enhance_done = Signal(object, object)  # (run_id, PIL|None), error str|None
    _status = Signal(str)
    _progress = Signal(int)

    _open_instance: "BgEnhanceDialog | None" = None

    # Queue depth max 1 (coalesced). Debounce scale flips so we don't thrash models.
    MAX_PENDING = 1
    SCALE_DEBOUNCE_MS = 400

    def __init__(self, rgba: Image.Image, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr["BgEnhance"]["Title"])
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setModal(True)
        self.resize(config.retouchWindowW, config.retouchWindowH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Scope to QDialog so bare props don't cascade onto child widgets.
        self.setStyleSheet(
            f"QDialog {{ background-color: {BG}; color: {TEXT}; border: none; }}"
        )

        self._source = rgba.convert("RGBA")
        self._result: Image.Image | None = None
        self._busy = False
        self._closed = False
        self._signals_live = True
        self._progress_value = 0
        self._run_id = 0
        self._cancel_event = threading.Event()
        self._pending_restart = False
        self._worker: threading.Thread | None = None
        self._apply_throttle = ClickThrottle(450)

        root = QVBoxLayout(self)
        m = DIALOG["pad"]
        root.setContentsMargins(m, m, m, m)
        root.setSpacing(DIALOG["rail_spacing"])

        # Scale dropdown
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(StrongBodyLabel(tr["BgEnhance"]["Scale"], self))
        self.scale_combo = AppCombo(self)
        self.scale_combo.setMinimumWidth(DIALOG["combo_min_w"])
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        top.addWidget(self.scale_combo, 1)
        root.addLayout(top)

        self.preview = BeforeAfterPreview(
            before_title=tr["BgEnhance"]["Current"],
            after_title=tr["BgEnhance"]["Enhanced"],
            after_placeholder=tr["BgEnhance"]["Enhanced"],
            parent=self,
        )
        self.preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview.show_before_rgba(self._source)
        root.addWidget(self.preview, 1)

        # Progress
        self.progress_panel = QWidget(self)
        prog = QVBoxLayout(self.progress_panel)
        prog.setContentsMargins(0, 0, 0, 0)
        prog.setSpacing(DIALOG["progress_spacing"])
        self.progress_label = BodyLabel(
            tr["BgEnhance"]["Processing"].format(0), self.progress_panel
        )
        self.progress_bar = ProgressBar(self.progress_panel)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        prog.addWidget(self.progress_label)
        prog.addWidget(self.progress_bar)
        self.progress_panel.setVisible(False)
        root.addWidget(self.progress_panel)

        self.status = BodyLabel(tr["BgEnhance"].get("ReadyHint", "Choose scale, then click Run."), self)
        root.addWidget(self.status)

        # Buttons: Cancel · Run · Apply
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        self.btn_cancel = make_button(tr["BgEnhance"]["Cancel"], "secondary", self)
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_cancel)
        self.btn_run = make_button(tr["BgEnhance"].get("Run", "Run"), "primary", self)
        self.btn_run.clicked.connect(self._on_run_clicked)
        buttons.addWidget(self.btn_run)
        self.btn_apply = make_button(tr["BgEnhance"]["Apply"], "secondary", self)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_apply)
        buttons.addWidget(self.btn_apply)
        root.addLayout(buttons)

        self._enhance_done.connect(self._on_enhance_done)
        self._status.connect(self.status.setText)
        self._progress.connect(self._on_progress)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(400)
        self._progress_timer.timeout.connect(self._tick_progress)

        # Rate-limited queue flusher (latest scale only) - used when Run while busy.
        self._queue_timer = QTimer(self)
        self._queue_timer.setSingleShot(True)
        self._queue_timer.setInterval(self.SCALE_DEBOUNCE_MS)
        self._queue_timer.timeout.connect(self._flush_enhance_queue)

        BgEnhanceDialog._open_instance = self
        self._fill_scale_combo()
        # Do not auto-run - user clicks Run.

    def _fill_scale_combo(self):
        apply_default_enhance_model()

        def _fetch():
            modes = selectable_modes()
            # x2 may not be on disk yet - still offer it (auto-download on run)
            return modes or [EnhanceMode.X2PLUS]

        current = config.enhanceMode.value
        current_data = getattr(current, "value", current)
        select = refresh_combo(
            self.scale_combo,
            _fetch,
            label_of=lambda m: tr["EnhanceMode"].get(m.name, m.name),
            data_of=lambda m: m.value,
            current=current_data,
        )
        modes = list(_fetch())
        if modes:
            config.set(config.enhanceMode, modes[select])

    def _selected_mode(self) -> EnhanceMode:
        data = self.scale_combo.currentData()
        if data is None:
            return EnhanceMode.X2PLUS
        try:
            return EnhanceMode(data) if isinstance(data, str) else data
        except Exception:
            return EnhanceMode.X2PLUS

    def _emit_status(self, text: str) -> None:
        if self._signals_live and not self._closed:
            self._status.emit(text)

    def _emit_progress(self, value: int) -> None:
        if self._signals_live and not self._closed:
            self._progress.emit(value)

    def _emit_done(self, payload, err) -> None:
        if self._signals_live:
            self._enhance_done.emit(payload, err)

    def _queue_restart(self, cancel_running: bool = True):
        """Enqueue at most one restart; rate-limit via debounce timer."""
        if self._closed:
            return
        # Hard queue limit: coalesce to a single pending slot.
        self._pending_restart = True
        if cancel_running and self._busy:
            self._signal_cancel()
        self._queue_timer.start(self.SCALE_DEBOUNCE_MS)

    def _flush_enhance_queue(self):
        """Run the latest queued enhance after debounce (queue depth ≤ 1)."""
        if self._closed or not self._pending_restart:
            return
        if self._busy:
            # Still draining previous job - keep the single pending slot and retry.
            self._queue_timer.start(self.SCALE_DEBOUNCE_MS)
            return
        self._pending_restart = False
        self._start_enhance()

    def _on_scale_changed(self, _index: int):
        mode = self._selected_mode()
        config.set(config.enhanceMode, mode)
        # Scale only selects the model - click Run to enhance (or re-run).

    def _on_run_clicked(self):
        if self._closed:
            return
        self._start_enhance()

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.scale_combo.setEnabled(self.scale_combo.count() > 0 and not self._closed)
        self.btn_run.setEnabled(not busy and not self._closed)
        self.btn_apply.setEnabled(not busy and self._result is not None and not self._closed)
        self.btn_cancel.setEnabled(True)
        if busy:
            self.progress_panel.setVisible(True)
            self._on_progress(0)
            self.preview.show_after_loading(tr["BgEnhance"]["Enhancing"])
        else:
            self._progress_timer.stop()

    @Slot(int)
    def _on_progress(self, value: int):
        if self._closed:
            return
        value = max(0, min(100, int(value)))
        if value >= 40 and value < 95 and self._busy and not self._progress_timer.isActive():
            self._progress_timer.start()
        if value >= 95:
            self._progress_timer.stop()
        self._progress_value = value
        self.progress_bar.setValue(value)
        self.progress_label.setText(tr["BgEnhance"]["Processing"].format(value))
        self.progress_panel.setVisible(True)

    def _tick_progress(self):
        if not self._busy or self._closed:
            self._progress_timer.stop()
            return
        if self._progress_value < 90:
            self._on_progress(self._progress_value + 1)

    def _signal_cancel(self):
        """Ask the worker to abort ASAP (does not bump run_id - needed for restart)."""
        from backend.tools.infer_client import InferClient

        self._cancel_event.set()
        InferClient.instance().cancel(run_id=self._run_id if self._run_id else None)

    def _abort_running(self):
        """Stop the in-flight enhance permanently (dialog closing). Clears restart queue."""
        self._run_id += 1
        self._pending_restart = False
        self._queue_timer.stop()
        self._signal_cancel()
        self._cleanup_temps()

    def _cleanup_temps(self):
        from backend.tools.infer_client import InferClient

        InferClient.unlink_quiet(getattr(self, "_temp_in", None))
        InferClient.unlink_quiet(getattr(self, "_temp_out", None))
        self._temp_in = None
        self._temp_out = None

    def _disconnect_worker_signals(self):
        """Prevent worker emits into a closing dialog (avoids segfaults)."""
        if not self._signals_live:
            return
        self._signals_live = False
        self._progress_timer.stop()
        self._queue_timer.stop()
        for signal, slot in (
            (self._enhance_done, self._on_enhance_done),
            (self._status, self.status.setText),
            (self._progress, self._on_progress),
        ):
            try:
                signal.disconnect(slot)
            except Exception:
                pass

    def _start_enhance(self):
        if self._closed:
            return
        # Never stack workers: coalesce into one pending restart (queue depth = 1).
        if self._busy:
            self._queue_restart(cancel_running=True)
            return

        from backend.tools.infer_client import InferClient
        from backend.tools.infer_protocol import JobType

        mode = self._selected_mode()
        self._run_id += 1
        run_id = self._run_id
        self._cancel_event = threading.Event()
        self._result = None
        self.btn_apply.setEnabled(False)
        self._set_busy(True)
        self.status.setText(tr["BgEnhance"]["Running"])
        self._cleanup_temps()

        client = InferClient.instance()
        self._temp_in = client.make_temp_path("enh_in_", ".png")
        self._temp_out = client.make_temp_path("enh_out_", ".png")
        self._source.save(self._temp_in, format="PNG")

        def on_progress(p: int):
            self._emit_progress(p)

        def on_log(msg: str):
            lower = msg.lower()
            if "download" in lower:
                self._emit_status(tr["BgEnhance"]["Downloading"])
            elif "load" in lower:
                self._emit_status(tr["BgEnhance"]["Loading"])
            else:
                self._emit_status(tr["BgEnhance"]["Enhancing"])

        def on_result(path: str):
            out = None
            err = None
            try:
                out = Image.open(path).convert("RGBA")
                out.load()
            except Exception as e:
                traceback.print_exc()
                err = str(e)
            finally:
                InferClient.unlink_quiet(path)
                InferClient.unlink_quiet(self._temp_in)
                self._temp_in = None
                self._temp_out = None
            self._emit_done((run_id, out), err)

        def on_error(msg: str):
            InferClient.unlink_quiet(self._temp_in)
            InferClient.unlink_quiet(self._temp_out)
            self._temp_in = None
            self._temp_out = None
            if msg in ("__cancelled__", "TIMEOUT", "CRASH", "BUSY"):
                if msg == "TIMEOUT":
                    self._emit_done(
                        (run_id, None),
                        "Enhance timed out (no progress). The worker was restarted - try again.",
                    )
                elif msg == "CRASH":
                    self._emit_done(
                        (run_id, None),
                        "Enhance worker crashed. The worker was restarted - try again.",
                    )
                elif msg == "BUSY":
                    self._emit_done(
                        (run_id, None),
                        "Another GPU job is already running. Wait for it to finish.",
                    )
                else:
                    self._emit_done((run_id, None), "__cancelled__")
            else:
                mapped = msg
                if "memory" in msg.lower() or "vram" in msg.lower():
                    mapped = (
                        "Not enough GPU memory for enhance. "
                        "Try a smaller image, x2 scale, or close other GPU apps."
                    )
                self._emit_done((run_id, None), mapped)

        client.start_job(
            JobType.ENHANCE,
            {
                "input_path": self._temp_in,
                "output_path": self._temp_out,
                "mode": mode.value,
                "hardware_acceleration": bool(config.hardwareAcceleration.value),
            },
            on_progress=on_progress,
            on_log=on_log,
            on_result=on_result,
            on_error=on_error,
            coalesce=True,
        )
        # Track that a job was submitted (no local thread).
        self._worker = None

    @Slot(object, object)
    def _on_enhance_done(self, payload, err):
        run_id, img = payload if isinstance(payload, tuple) else (self._run_id, payload)
        cancelled = err == "__cancelled__"
        self._progress_timer.stop()

        if self._closed:
            self._busy = False
            self._pending_restart = False
            self._queue_timer.stop()
            return

        # After any finish: if a restart is queued, rate-limit it (do not stack).
        if self._pending_restart:
            self._set_busy(False)
            self._result = None
            if cancelled or err or run_id == self._run_id:
                self._queue_timer.start(self.SCALE_DEBOUNCE_MS)
            return

        if cancelled:
            self._result = None
            self._set_busy(False)
            if run_id != self._run_id:
                return
            self.progress_panel.setVisible(False)
            self.preview.hide_after()
            self.status.setText(tr["BgEnhance"].get("Cancelled", "Enhance cancelled."))
            self.btn_apply.setEnabled(False)
            self.btn_run.setEnabled(True)
            return

        if run_id != self._run_id:
            return

        if err:
            self._result = None
            self._set_busy(False)
            self.progress_panel.setVisible(False)
            self.preview.hide_after()
            self.status.setText(tr["BgEnhance"]["Failed"].format(err))
            self.btn_apply.setEnabled(False)
            self.btn_run.setEnabled(True)
            return

        self._on_progress(100)
        self._result = img
        self._set_busy(False)
        if img is not None:
            self.preview.show_after_rgba(img)
            w, h = img.size
            self.status.setText(tr["BgEnhance"]["Done"].format(w, h))
            self.btn_apply.setEnabled(True)
            self.btn_run.setEnabled(True)
        QTimer.singleShot(config.retouchProgressHideMs, self._hide_progress)

    def _hide_progress(self):
        if not self._busy and not self._closed:
            self.progress_panel.setVisible(False)
            self.progress_bar.setValue(0)
            self._progress_value = 0

    def _on_apply(self):
        if self._busy or self._result is None or self._closed:
            return
        if not self._apply_throttle.allow():
            return
        self._pending_restart = False
        self._queue_timer.stop()
        self.btn_apply.setEnabled(False)
        self.finished_image.emit(self._result)
        self.accept()

    def _shutdown(self):
        """Cancel queue, stop worker signals, mark closed."""
        if self._closed:
            self._abort_running()
            return
        self._closed = True
        self._busy = False
        self._abort_running()
        self._disconnect_worker_signals()
        if BgEnhanceDialog._open_instance is self:
            BgEnhanceDialog._open_instance = None

    def wait_worker(self, timeout: float = 60.0) -> bool:
        """Best-effort wait - infer jobs finish via signals; return True if not busy."""
        import time

        end = time.monotonic() + timeout
        while self._busy and time.monotonic() < end:
            time.sleep(0.05)
        return not self._busy

    def reject(self):
        self._shutdown()
        super().reject()

    def accept(self):
        self._pending_restart = False
        self._queue_timer.stop()
        self._shutdown()
        super().accept()

    def closeEvent(self, event):
        self._shutdown()
        super().closeEvent(event)

    @classmethod
    def is_open(cls) -> bool:
        return cls._open_instance is not None
