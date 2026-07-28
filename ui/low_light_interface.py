"""Low Light tab - MIRNet (PyTorch) image enhancement, images only."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import MessageBox

from backend.config import config, tr
from backend.tools import diag
from backend.tools.common_tools import is_image_file
from backend.tools.constant import LowLightMode
from backend.tools.infer_client import InferClient
from backend.tools.infer_protocol import JobType
from backend.tools.low_light_models import (
    apply_default_low_light_model,
    selectable_modes,
)
from ui.component.controls.inputs import make_section_combo, refresh_combo
from ui.component.preview.before_after_preview import BeforeAfterPreview
from ui.component.workspace.action_bar import RailActions
from ui.component.workspace.task_list_component import TaskStatus
from ui.component.workspace.workspace_page import WorkspacePage
from ui.shell import ContentPage
from ui.theme import FORM


def _preview_temp_path(source_path: str) -> str:
    d = Path(tempfile.gettempdir()) / "midgard_low_light"
    d.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem[:48] or "preview"
    fd, path = tempfile.mkstemp(suffix=".png", prefix=f"{stem}_", dir=str(d))
    os.close(fd)
    return path


def _unlink_quiet(path: str | None):
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


class LowLightInterface(ContentPage):
    append_log_signal = Signal(list)
    task_status_signal = Signal(int, object)
    preview_path_signal = Signal(str)
    toggle_buttons_signal = Signal(bool)
    select_task_signal = Signal(int)
    progress_signal = Signal(int, int)
    task_error_signal = Signal(str)
    processing_changed = Signal(bool)
    save_enabled_signal = Signal(bool)
    alert_signal = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__("LowLightInterface", parent=parent)
        self._stop_event = threading.Event()
        self._worker_thread = None
        self.current_processing_task_index = -1
        self.current_image_path = None
        self._installing = False
        self._processing = False
        self._external_gpu_busy = False
        self._active_run_id: int | None = None

        self.__init_widgets()
        self.append_log_signal.connect(self.append_log)
        self.task_status_signal.connect(
            lambda idx, status: self.task_list_component.update_task_status(idx, status)
        )
        self.preview_path_signal.connect(self._on_preview_path)
        self.toggle_buttons_signal.connect(self._toggle_buttons)
        self.select_task_signal.connect(self.task_list_component.select_task)
        self.progress_signal.connect(self._on_progress)
        self.task_error_signal.connect(self._on_task_error)
        self.save_enabled_signal.connect(self.action_bar.set_save_enabled)
        self.alert_signal.connect(self._show_alert)
        self.append_output(tr["LowLight"]["EmptyStateHint"])
        self._refresh_model_combo()

    def __init_widgets(self):
        ll = tr["LowLight"]
        self.preview = BeforeAfterPreview(
            upload_hint=ll.get("SelectImageTitle", ll["UploadImage"]),
            before_title=ll["Before"],
            after_title=ll["After"],
            after_placeholder=ll["After"],
            parent=self,
        )
        self.before_view = self.preview.before_view
        self.after_view = self.preview.after_view
        self.preview.empty_clicked.connect(self.open_file)
        self.preview.files_dropped.connect(self._open_paths)

        settings_host = QWidget(self)
        settings_layout = QVBoxLayout(settings_host)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(FORM["field_spacing"])

        self.model_field = make_section_combo(
            settings_host,
            label=ll["Model"],
            tooltip=ll["ModelDesc"],
            fetch=selectable_modes,
            label_of=lambda m: tr["LowLightMode"].get(m.name, m.name),
            data_of=lambda m: m.value,
            current=getattr(config.lowLightMode.value, "value", config.lowLightMode.value),
            on_change=self._on_model_selected,
        )
        self.model_combo = self.model_field.control
        settings_layout.addWidget(self.model_field)

        self.workspace = WorkspacePage(
            preview=self.preview,
            settings=settings_host,
            actions=RailActions(
                open_text=ll["Open"],
                run_text=ll["Run"],
                stop_text=ll["Stop"],
                stop_confirm_title=ll["StopConfirmTitle"],
                stop_confirm_desc=ll["StopConfirmDesc"],
                reset_text=ll["Reset"],
                reset_confirm_title=ll["ResetConfirmTitle"],
                reset_confirm_desc=ll["ResetConfirmDesc"],
                empty_list_hint=ll["EmptyListHint"],
                save_text=ll["Save"],
                settings_title=tr["SubtitleExtractorGUI"]["Setting"],
                progress_label=ll.get("ProgressLabel", "Processing {}%"),
            ),
            parent=self,
            preview_title=ll["Preview"],
            preview_bordered=True,
        )
        self.log_panel = self.workspace.log_panel
        self.task_list_component = self.workspace.task_list_component
        self.action_bar = self.workspace.action_bar
        self.action_bar.open_clicked.connect(self.open_file)
        self.action_bar.run_clicked.connect(self.run_button_clicked)
        self.action_bar.stop_confirmed.connect(self._on_stop_confirmed)
        self.action_bar.save_clicked.connect(self.save_button_clicked)
        self.action_bar.reset_confirmed.connect(self.reset_workspace)
        self.task_list_component.task_selected.connect(self.on_task_selected)
        self.task_list_component.task_deleted.connect(self.on_task_deleted)

        self.body.addWidget(self.workspace)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_model_combo()

    def _on_model_selected(self, data):
        try:
            mode = LowLightMode(data) if isinstance(data, str) else data
            config.set(config.lowLightMode, mode)
        except Exception:
            pass

    def _show_alert(self, title: str, content: str):
        box = MessageBox(title, content, self.window())
        box.yesButton.hide()
        box.cancelButton.setText(tr["Common"].get("OK", "OK"))
        box.buttonLayout.insertStretch(0, 1)
        box.exec()

    def _selected_mode(self) -> LowLightMode | None:
        data = self.model_combo.currentData()
        if data is None:
            return None
        try:
            return LowLightMode(data) if isinstance(data, str) else data
        except Exception:
            return None

    def refresh_models(self):
        self._refresh_model_combo()

    def set_install_busy(self, busy: bool):
        self._installing = busy
        self._apply_app_lock()

    def set_external_gpu_busy(self, busy: bool):
        self._external_gpu_busy = bool(busy)
        self._apply_app_lock()

    def _refresh_model_combo(self):
        apply_default_low_light_model()
        current = config.lowLightMode.value
        current_data = getattr(current, "value", current)
        select = refresh_combo(
            self.model_combo,
            selectable_modes,
            label_of=lambda m: tr["LowLightMode"].get(m.name, m.name),
            data_of=lambda m: m.value,
            current=current_data,
        )
        modes = selectable_modes()
        if modes:
            config.set(config.lowLightMode, modes[select])
        self.model_combo.setEnabled(
            bool(modes)
            and not self._installing
            and not self._processing
            and not self._external_gpu_busy
        )

    def _apply_app_lock(self):
        idle = (
            not self._installing
            and not self._processing
            and not self._external_gpu_busy
        )
        self.action_bar.set_open_enabled(idle)
        self.action_bar.set_run_enabled(idle)
        self.action_bar.set_reset_enabled(idle)
        self.action_bar.set_save_enabled(idle and self._current_has_unsaved_preview())
        self.model_combo.setEnabled(idle and self.model_combo.count() > 0)
        if self._processing:
            self.action_bar.set_running(True)
        elif not self._installing:
            self.action_bar.set_running(False)

    def _current_has_unsaved_preview(self) -> bool:
        idx = self.task_list_component.get_current_task_index()
        task = self.task_list_component.get_task(idx)
        if not task:
            return False
        return bool(task.preview_temp_path and os.path.isfile(task.preview_temp_path))

    @Slot(bool)
    def _toggle_buttons(self, show_run):
        self._processing = not show_run
        self._apply_app_lock()
        self.processing_changed.emit(self._processing)

    @Slot(int, int)
    def _on_progress(self, index, progress):
        self.task_list_component.update_task_progress(index, progress)
        self.action_bar.set_progress(progress)

    @Slot(str)
    def _on_preview_path(self, path: str):
        try:
            self.preview.show_after_rgba(Image.open(path).convert("RGBA"))
        except Exception:
            self.preview.hide_after()
        idx = self.current_processing_task_index
        if idx < 0:
            idx = self.task_list_component.get_current_task_index()
        task = self.task_list_component.get_task(idx)
        if task:
            if task.preview_temp_path and task.preview_temp_path != path:
                _unlink_quiet(task.preview_temp_path)
            task.preview_temp_path = path
            task.saved = False
        self.save_enabled_signal.emit(True)

    @Slot(str)
    def _on_task_error(self, message: str):
        self.append_output(tr["LowLight"]["Error"].format(self._format_error_text(message)))
        if self.current_processing_task_index >= 0:
            self.task_list_component.update_task_status(
                self.current_processing_task_index, TaskStatus.FAILED
            )
            if self.after_view._source is None:
                self.preview.set_after_error(
                    tr["LowLight"]["Error"].format(self._format_error_text(message))
                )

    def on_task_selected(self, index, path):
        self.current_image_path = path
        self.preview.show_before(path, on_error_hint=tr["LowLight"]["OpenFailed"].format(path))
        task = self.task_list_component.get_task(index)
        preview = task.preview_temp_path if task else None
        if preview and os.path.isfile(preview):
            try:
                self.preview.show_after_rgba(Image.open(preview).convert("RGBA"))
            except Exception:
                self.preview.hide_after()
        elif task and task.saved and task._output_path and os.path.isfile(task._output_path):
            try:
                self.preview.show_after_rgba(Image.open(task._output_path).convert("RGBA"))
            except Exception:
                self.preview.hide_after()
        elif self._processing and index == self.current_processing_task_index:
            self.preview.show_after_loading(tr["LowLight"]["AfterLoading"])
        else:
            self.preview.hide_after()
        self.action_bar.set_save_enabled(
            not self._processing and not self._installing and self._current_has_unsaved_preview()
        )

    def on_task_deleted(self, index, task):
        if task is not None:
            _unlink_quiet(getattr(task, "preview_temp_path", None))

        if self.current_processing_task_index == index:
            self._abort_current_process()
            self.current_processing_task_index = -1
        elif self.current_processing_task_index > index:
            self.current_processing_task_index -= 1

        remaining = len(self.task_list_component.get_all_tasks())
        if remaining == 0:
            self.current_image_path = None
            self.preview.show_empty(
                tr["LowLight"].get("SelectImageTitle", tr["LowLight"]["UploadImage"])
            )
            self.action_bar.set_save_enabled(False)
            self.append_output(tr["TaskList"]["TaskRemovedEmpty"])
            return

        next_idx = min(index, remaining - 1)
        self.task_list_component.select_task(next_idx)
        self.append_output(tr["TaskList"]["TaskRemoved"].format(task.name if task else ""))

    def _abort_current_process(self):
        self._stop_event.set()
        rid = self._active_run_id
        if rid is not None:
            InferClient.instance().cancel(rid)
        else:
            InferClient.instance().cancel()
        self._active_run_id = None
        self._processing = False
        self._apply_app_lock()
        self.processing_changed.emit(False)

    def open_file(self):
        if self._installing or self._processing:
            return
        diag.upload("Open / Upload low-light image(s)")
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            tr["LowLight"]["Open"],
            "",
            "Image Files (*.jpg *.jpeg *.png *.bmp *.webp *.tiff *.tif);;All Files (*.*)",
        )
        if files:
            self._open_paths(files)

    def _open_paths(self, files):
        if self._installing or self._processing:
            return
        if not files:
            return
        loaded = []
        for path in reversed(list(files)):
            if not is_image_file(path):
                self.append_output(tr["LowLight"]["ImagesOnly"].format(path))
                continue
            try:
                with Image.open(path) as im:
                    im.verify()
                Image.open(path).close()
            except Exception:
                self.append_output(tr["LowLight"]["OpenFailed"].format(path))
                continue
            loaded.append(path)
            self.append_output(tr["LowLight"]["OpenSuccess"].format(path))
        for path in reversed(loaded):
            self.task_list_component.add_task(path, output_suffix="_lowlight")
            index = max(0, self.task_list_component.find_task_index_by_path(path))
            self.task_list_component.select_task(index)

    def _on_stop_confirmed(self):
        diag.run("Stop confirmed - aborting low-light")
        self._stop_event.set()
        rid = self._active_run_id
        if rid is not None:
            InferClient.instance().cancel(rid)
        else:
            InferClient.instance().cancel()
        self._active_run_id = None
        if self.current_processing_task_index >= 0:
            self.task_list_component.update_task_status(
                self.current_processing_task_index, TaskStatus.STOPPED
            )
            self.task_list_component.update_task_progress(
                self.current_processing_task_index, 0
            )
        self._processing = False
        self._apply_app_lock()
        self.processing_changed.emit(False)
        if not self._current_has_unsaved_preview():
            self.preview.hide_after()
        self.append_output(tr["LowLight"]["Stopped"])

    def reset_workspace(self):
        if self._processing or self._installing:
            return
        for task in self.task_list_component.get_all_tasks():
            _unlink_quiet(getattr(task, "preview_temp_path", None))
        self.task_list_component.clear_tasks()
        self.current_image_path = None
        self.current_processing_task_index = -1
        self.preview.show_empty(
            tr["LowLight"].get("SelectImageTitle", tr["LowLight"]["UploadImage"])
        )
        self.action_bar.set_save_enabled(False)
        self.log_panel.clear()
        self.append_output(tr["LowLight"]["EmptyStateHint"])
        try:
            InferClient.instance().release()
        except Exception:
            pass

    def save_button_clicked(self):
        if self._processing or self._installing:
            return
        idx = self.task_list_component.get_current_task_index()
        task = self.task_list_component.get_task(idx)
        if not task or not task.preview_temp_path or not os.path.isfile(task.preview_temp_path):
            self.append_output(tr["LowLight"]["OpenFirst"])
            return
        default_name = f"{Path(task.path).stem}_lowlight.png"
        out_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            tr["LowLight"]["Save"],
            default_name,
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;All Files (*.*)",
        )
        if not out_path:
            return
        try:
            img = Image.open(task.preview_temp_path)
            ext = Path(out_path).suffix.lower()
            if ext in (".jpg", ".jpeg"):
                img.convert("RGB").save(out_path, quality=95)
            else:
                if not ext:
                    out_path = out_path + ".png"
                img.save(out_path)
            task.saved = True
            task._output_path = out_path
            self.append_output(tr["LowLight"]["SaveSuccess"].format(out_path))
            self.action_bar.set_save_enabled(False)
        except Exception as e:
            self.append_output(tr["LowLight"]["SaveFailed"].format(str(e)))

    def run_button_clicked(self):
        if self._processing or self._installing or self._external_gpu_busy:
            if self._external_gpu_busy:
                from ui.gpu_busy import gpu_busy_message

                self._show_alert(
                    tr["LowLight"].get("Title", "Low Light"),
                    gpu_busy_message(),
                )
            return
        mode = self._selected_mode()
        if mode is None:
            self.append_output(tr["LowLight"]["NoSelectableModel"])
            return
        pending = self.task_list_component.get_pending_tasks()
        if not pending:
            # Re-queue completed tasks so Run can re-process
            for i, task in enumerate(self.task_list_component.get_all_tasks()):
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED):
                    self.task_list_component.update_task_status(i, TaskStatus.PENDING)
                    self.task_list_component.update_task_progress(i, 0)
            pending = self.task_list_component.get_pending_tasks()
        if not pending:
            self.append_output(tr["LowLight"]["OpenFirst"])
            return

        self._stop_event.clear()
        self.toggle_buttons_signal.emit(False)
        self.processing_changed.emit(True)
        mode_value = mode.value

        def task():
            try:
                while not self._stop_event.is_set():
                    pending_tasks = self.task_list_component.get_pending_tasks()
                    if not pending_tasks:
                        break
                    self.current_processing_task_index, task_item = pending_tasks[0]
                    if not is_image_file(task_item.path):
                        self.append_log_signal.emit(
                            [tr["LowLight"]["ImagesOnly"].format(task_item.path)]
                        )
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.FAILED
                        )
                        continue

                    self.select_task_signal.emit(self.current_processing_task_index)
                    self.task_status_signal.emit(
                        self.current_processing_task_index, TaskStatus.PROCESSING
                    )
                    self.progress_signal.emit(self.current_processing_task_index, 1)

                    _unlink_quiet(task_item.preview_temp_path)
                    task_item.preview_temp_path = None
                    task_item.saved = False
                    preview_path = _preview_temp_path(task_item.path)
                    name = Path(task_item.path).name
                    diag.run(f"low-light processing  {name}  model={mode_value}")

                    ok = self._run_worker_process(
                        task_item.path,
                        preview_path,
                        mode_value,
                        display_name=name,
                    )
                    if self._stop_event.is_set():
                        _unlink_quiet(preview_path)
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.STOPPED
                        )
                        self.progress_signal.emit(self.current_processing_task_index, 0)
                        break
                    if ok:
                        task_item.preview_temp_path = preview_path
                        self.progress_signal.emit(self.current_processing_task_index, 100)
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.COMPLETED
                        )
                        self.append_log_signal.emit(
                            [tr["LowLight"]["Finished"].format(Path(task_item.path).name)]
                        )
                        self.save_enabled_signal.emit(True)
                    else:
                        _unlink_quiet(preview_path)
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.FAILED
                        )
                        break
            finally:
                self._active_run_id = None
                self.toggle_buttons_signal.emit(True)
                self.current_processing_task_index = -1

        self._worker_thread = threading.Thread(target=task, daemon=True)
        self._worker_thread.start()

    def _run_worker_process(
        self,
        input_path: str,
        preview_path: str,
        mode_value: str,
        *,
        display_name: str | None = None,
    ) -> bool:
        task_index = self.current_processing_task_index
        success = {"ok": True}
        done = threading.Event()
        name = display_name or Path(input_path).name
        started = {"yes": False}

        def on_progress(p: int):
            if not started["yes"]:
                started["yes"] = True
                self.append_log_signal.emit(
                    [tr["LowLight"]["Processing"].format(name, mode_value)]
                )
            self.progress_signal.emit(task_index, max(1, min(99, int(p))))

        def on_log(msg: str):
            text = str(msg or "")
            lower = text.lower()
            if lower.startswith("queued"):
                self.append_log_signal.emit([text])
                return
            self.append_log_signal.emit([text])

        def on_error(msg: str):
            if msg == "__cancelled__":
                success["ok"] = False
            elif msg in ("TIMEOUT", "CRASH", "BUSY"):
                success["ok"] = False
                text = {
                    "TIMEOUT": "Low-light enhance timed out. The worker was restarted - try again.",
                    "CRASH": "Low-light worker crashed. Try again.",
                    "BUSY": "Another GPU job is already running. Wait or stop it first.",
                }.get(msg, "Low-light worker crashed. Try again.")
                self.task_error_signal.emit(text)
            else:
                success["ok"] = False
                self.task_error_signal.emit(msg)
            done.set()

        def on_result(path: str):
            self.preview_path_signal.emit(path)
            self.progress_signal.emit(task_index, 100)
            done.set()

        def on_done():
            done.set()

        if self._stop_event.is_set():
            return False

        payload = {
            "input_path": input_path,
            "output_path": preview_path,
            "mode": mode_value,
            "hardware_acceleration": bool(config.hardwareAcceleration.value),
            # Make the terminal callback a model/VRAM-release barrier before
            # this queue submits its next image.
            "release_after_job": True,
        }

        client = InferClient.instance()
        run_id = client.start_job(
            JobType.LOW_LIGHT,
            payload,
            on_progress=on_progress,
            on_log=on_log,
            on_result=on_result,
            on_error=on_error,
            on_done=on_done,
            coalesce=False,
        )
        self._active_run_id = run_id if run_id >= 0 else None
        while not done.wait(timeout=0.25):
            if self._stop_event.is_set():
                if self._active_run_id is not None:
                    client.cancel(self._active_run_id)
                else:
                    client.cancel()
                self._active_run_id = None
                return False
        self._active_run_id = None
        return success["ok"] and not self._stop_event.is_set()

    def _format_error_text(self, text: str) -> str:
        lower = (text or "").lower()
        if "out of memory" in lower or "vram" in lower or "cuda" in lower and "memory" in lower:
            return tr["LowLight"]["ErrorOutOfMemory"]
        if "download" in lower or "html page" in lower:
            return tr["LowLight"]["ErrorDownload"]
        return text

    @Slot(list)
    def append_log(self, log):
        self.append_output(*log)

    def append_output(self, *args):
        self.log_panel.append(*args)
