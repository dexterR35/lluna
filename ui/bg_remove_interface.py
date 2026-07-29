"""Background removal tab - images only (no video engine)."""

from __future__ import annotations

import gc
import os
import shutil
import tempfile
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import MessageBox

from backend.config import config, tr
from backend.tools import diag
from backend.tools.bg_remove_models import (
    apply_default_bg_model,
    selectable_modes,
)
from backend.tools.common_tools import is_image_file
from backend.tools.constant import BgRemoveMode
from backend.tools.infer_client import InferClient
from backend.tools.infer_protocol import JobType
from ui.component.workspace.action_bar import RailActions
from ui.component.preview.before_after_preview import BeforeAfterPreview
from ui.component.controls.button_styles import make_button, make_toggle_button, paint_toggle_button
from ui.component.controls.inputs import (
    LabeledField,
    make_install_model_button,
    make_section_combo,
    refresh_combo,
    show_install_model_when_empty,
)
from ui.component.workspace.task_list_component import Task, TaskStatus
from ui.component.workspace.workspace_page import WorkspacePage
from ui.shell import ContentPage
from ui.theme import FORM

_MODE_AUTOMATIC = "automatic"
_MODE_PROTECT = "protect"


def _preview_temp_path(source_path: str) -> str:
    """Temp PNG for preview only - final save happens via Save button."""
    d = Path(tempfile.gettempdir()) / "midgard_bg"
    d.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem[:48] or "preview"
    fd, path = tempfile.mkstemp(suffix=".png", prefix=f"{stem}_", dir=str(d))
    os.close(fd)
    return path


def _protect_temp_path(source_path: str) -> str:
    """Temp L-mask PNG for protect-areas keep mask."""
    d = Path(tempfile.gettempdir()) / "midgard_bg"
    d.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem[:48] or "protect"
    fd, path = tempfile.mkstemp(suffix=".png", prefix=f"{stem}_keep_", dir=str(d))
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


def _task_has_protect_mask(task: Task | None) -> bool:
    if not task or not task.protect_mask_path:
        return False
    return os.path.isfile(task.protect_mask_path)


class BgRemoveInterface(ContentPage):
    append_log_signal = Signal(list)
    task_status_signal = Signal(int, object)
    preview_path_signal = Signal(str)
    toggle_buttons_signal = Signal(bool)
    select_task_signal = Signal(int)
    progress_signal = Signal(int, int)  # index, progress
    task_error_signal = Signal(str)
    processing_changed = Signal(bool)
    install_models_requested = Signal()
    save_enabled_signal = Signal(bool)
    alert_signal = Signal(str, str)  # title, content - UI-thread MessageBox

    def __init__(self, parent=None):
        super().__init__("BgRemoveInterface", parent=parent)
        self._stop_event = threading.Event()
        self._worker_thread = None
        self.running_process = None
        self.current_processing_task_index = -1
        self.current_image_path = None
        self._installing = False
        self._processing = False
        self._external_gpu_busy = False
        self._run_mode = _MODE_AUTOMATIC
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
        self.save_enabled_signal.connect(self.action_bar.set_retouch_enabled)
        self.alert_signal.connect(self._show_alert)
        self.append_output(tr["BgRemove"]["EmptyStateHint"])
        self._refresh_model_combo()
        self._update_protect_controls()

    def __init_widgets(self):
        bg = tr["BgRemove"]
        self.preview = BeforeAfterPreview(
            upload_hint=bg.get("SelectImageTitle", bg["UploadImage"]),
            before_title=bg["Before"],
            after_title=bg["After"],
            after_placeholder=bg["After"],
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
            label=tr["BgRemove"]["Model"],
            tooltip=tr["BgRemove"]["ModelDesc"],
            fetch=selectable_modes,
            label_of=lambda m: tr["BgRemoveMode"].get(m.name, m.name),
            data_of=lambda m: m.value,
            current=getattr(config.bgRemoveMode.value, "value", config.bgRemoveMode.value),
            on_change=self._on_model_selected,
        )
        self.model_combo = self.model_field.control
        settings_layout.addWidget(self.model_field)
        self.install_model_button = make_install_model_button(
            settings_host, self.install_models_requested.emit
        )
        settings_layout.addWidget(self.install_model_button)

        # Run mode: Automatic | Protect areas
        mode_wrap = QWidget(settings_host)
        mode_row = QHBoxLayout(mode_wrap)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(FORM["field_spacing"])
        self._mode_group = QButtonGroup(self)
        self.btn_mode_auto = make_toggle_button(bg["ModeAutomatic"], mode_wrap)
        self.btn_mode_protect = make_toggle_button(bg["ModeProtect"], mode_wrap)
        for btn in (self.btn_mode_auto, self.btn_mode_protect):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._mode_group.addButton(btn)
            mode_row.addWidget(btn)
        self.btn_mode_auto.setChecked(True)
        paint_toggle_button(self.btn_mode_auto)
        paint_toggle_button(self.btn_mode_protect)
        self.btn_mode_auto.clicked.connect(lambda: self._set_run_mode(_MODE_AUTOMATIC))
        self.btn_mode_protect.clicked.connect(lambda: self._set_run_mode(_MODE_PROTECT))
        self.mode_field = LabeledField(
            bg["RunMode"],
            mode_wrap,
            settings_host,
            tooltip=bg["RunModeDesc"],
        )
        settings_layout.addWidget(self.mode_field)

        self.btn_edit_protect = make_button(bg["EditKeepMask"], "warning", settings_host)
        self.btn_edit_protect.setToolTip(bg["EditKeepMaskTip"])
        self.btn_edit_protect.clicked.connect(self._edit_protect_mask_current)
        settings_layout.addWidget(self.btn_edit_protect)

        self.workspace = WorkspacePage(
            preview=self.preview,
            settings=settings_host,
            actions=RailActions(
                open_text=bg["Open"],
                run_text=bg["Run"],
                stop_text=bg["Stop"],
                stop_confirm_title=bg["StopConfirmTitle"],
                stop_confirm_desc=bg["StopConfirmDesc"],
                reset_text=bg["Reset"],
                reset_confirm_title=bg["ResetConfirmTitle"],
                reset_confirm_desc=bg["ResetConfirmDesc"],
                empty_list_hint=bg["EmptyListHint"],
                save_text=bg["Save"],
                retouch_text=bg["Retouch"],
                settings_title=tr["SubtitleExtractorGUI"]["Setting"],
                progress_label=bg.get("ProgressLabel", "Processing {}%"),
            ),
            parent=self,
            preview_title=bg["Preview"],
            preview_bordered=True,
        )
        self.log_panel = self.workspace.log_panel
        self.task_list_component = self.workspace.task_list_component
        self.action_bar = self.workspace.action_bar
        self.action_bar.open_clicked.connect(self.open_file)
        self.action_bar.run_clicked.connect(self.run_button_clicked)
        self.action_bar.stop_confirmed.connect(self._on_stop_confirmed)
        self.action_bar.save_clicked.connect(self.save_button_clicked)
        self.action_bar.retouch_clicked.connect(self.retouch_button_clicked)
        self.action_bar.reset_confirmed.connect(self.reset_workspace)
        self.task_list_component.task_selected.connect(self.on_task_selected)
        self.task_list_component.task_deleted.connect(self.on_task_deleted)

        self.body.addWidget(self.workspace)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_model_combo()

    def _on_model_selected(self, data):
        try:
            mode = BgRemoveMode(data) if isinstance(data, str) else data
            config.set(config.bgRemoveMode, mode)
        except Exception:
            pass

    def _is_protect_mode(self) -> bool:
        return self._run_mode == _MODE_PROTECT

    def _set_run_mode(self, mode: str):
        self._run_mode = mode if mode in (_MODE_AUTOMATIC, _MODE_PROTECT) else _MODE_AUTOMATIC
        self.btn_mode_auto.setChecked(self._run_mode == _MODE_AUTOMATIC)
        self.btn_mode_protect.setChecked(self._run_mode == _MODE_PROTECT)
        paint_toggle_button(self.btn_mode_auto)
        paint_toggle_button(self.btn_mode_protect)
        self._update_protect_controls()

    def _update_protect_controls(self):
        protect = self._is_protect_mode()
        idle = not self._processing and not self._installing
        self.btn_edit_protect.setVisible(protect)
        task = self.task_list_component.get_task(
            self.task_list_component.get_current_task_index()
        )
        has_image = bool(task and task.path)
        self.btn_edit_protect.setEnabled(protect and idle and has_image)

    def _edit_protect_mask_current(self):
        if self._processing or self._installing or not self._is_protect_mode():
            return
        diag.event("Edit Keep Mask requested")
        task = self.task_list_component.get_task(
            self.task_list_component.get_current_task_index()
        )
        if not task:
            self.append_output(tr["BgRemove"]["OpenFirst"])
            return
        self._edit_protect_mask(task)

    def _edit_protect_mask(self, task: Task) -> bool:
        """Open keep-mask editor. Returns True if user saved (mask may be empty)."""
        try:
            with Image.open(task.path) as im:
                rgba = ImageOps.exif_transpose(im).convert("RGBA")
        except Exception as e:
            self.append_output(tr["BgRemove"]["OpenFailed"].format(f"{task.path}: {e}"))
            return False

        initial = None
        if _task_has_protect_mask(task):
            try:
                initial = np.asarray(Image.open(task.protect_mask_path).convert("L"))
            except Exception:
                initial = None

        from ui.bg_protect_dialog import BgProtectDialog
        from ui.component.workspace.editor_page import present_editor_dialog

        dlg = BgProtectDialog(rgba, parent=self.window(), initial_mask=initial)
        mode = present_editor_dialog(dlg, rgba.size)
        had = "yes" if initial is not None and np.any(initial) else "no"
        diag.event(
            f"Edit Keep Mask dialog SHOW  {rgba.size[0]}x{rgba.size[1]}  "
            f"initial_mask={had}  mode={mode}"
        )
        saved: dict = {"ok": False, "mask": None}

        def on_mask(mask):
            saved["ok"] = True
            saved["mask"] = mask

        dlg.finished_mask.connect(on_mask)
        result = dlg.exec()
        try:
            dlg.finished_mask.disconnect(on_mask)
        except Exception:
            pass
        if result != QDialog.DialogCode.Accepted or not saved["ok"]:
            diag.event("Edit Keep Mask cancelled / closed")
            self.append_output(tr["BgRemove"]["ProtectMaskCancelled"])
            self._update_protect_controls()
            return False

        mask = saved["mask"]
        if mask is None or not np.any(mask):
            _unlink_quiet(task.protect_mask_path)
            task.protect_mask_path = None
            self.append_output(
                tr["BgRemove"]["ProtectMaskCleared"].format(Path(task.path).name)
            )
            self._requeue_task_for_rerun(task)
            self._update_protect_controls()
            return True

        path = task.protect_mask_path or _protect_temp_path(task.path)
        try:
            Image.fromarray(np.asarray(mask, dtype=np.uint8), mode="L").save(
                path, format="PNG"
            )
        except Exception as e:
            self.append_output(tr["BgRemove"]["SaveFailed"].format(str(e)))
            return False
        task.protect_mask_path = path
        self.append_output(
            tr["BgRemove"]["ProtectMaskReady"].format(Path(task.path).name)
        )
        self._requeue_task_for_rerun(task)
        self._update_protect_controls()
        return True

    def _requeue_task_for_rerun(self, task: Task) -> bool:
        """Put a completed/failed task back to Pending so Run will process it again."""
        if self._processing or task is None:
            return False
        if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return False
        idx = -1
        for i, t in enumerate(self.task_list_component.get_all_tasks()):
            if t is task:
                idx = i
                break
        if idx < 0:
            try:
                idx = self.task_list_component.find_task_index_by_path(task.path)
            except Exception:
                idx = -1
        if idx < 0:
            return False
        self.task_list_component.update_task_status(idx, TaskStatus.PENDING)
        self.task_list_component.update_task_progress(idx, 0)
        self.append_output(
            tr["BgRemove"].get(
                "ProtectMaskRequeued",
                "Ready to re-run {}. Click Run.",
            ).format(Path(task.path).name)
        )
        return True

    def _show_alert(self, title: str, content: str):
        box = MessageBox(title, content, self.window())
        box.yesButton.hide()
        box.cancelButton.setText(tr["Common"].get("OK", "OK"))
        box.buttonLayout.insertStretch(0, 1)
        box.exec()

    def _alert_protect_mask_required(self):
        msg = tr["BgRemove"]["ProtectMaskRequired"]
        self.append_output(msg)
        self._show_alert(tr["BgRemove"]["ProtectMaskRequiredTitle"], msg)

    def _ensure_protect_mask(self, task: Task) -> bool:
        """True if task already has a painted keep mask."""
        return _task_has_protect_mask(task)

    def _selected_mode(self) -> BgRemoveMode | None:
        """Mode currently shown in the dropdown (source of truth for Run)."""
        data = self.model_combo.currentData()
        if data is None:
            return None
        try:
            return BgRemoveMode(data) if isinstance(data, str) else data
        except Exception:
            return None

    def refresh_models(self):
        self._refresh_model_combo()

    def set_install_busy(self, busy: bool):
        self._installing = busy
        self._apply_app_lock()

    def _refresh_model_combo(self):
        apply_default_bg_model()
        current = config.bgRemoveMode.value
        current_data = getattr(current, "value", current)
        select = refresh_combo(
            self.model_combo,
            selectable_modes,
            label_of=lambda m: tr["BgRemoveMode"].get(m.name, m.name),
            data_of=lambda m: m.value,
            current=current_data,
        )
        modes = selectable_modes()
        if modes:
            config.set(config.bgRemoveMode, modes[select])
        show_install_model_when_empty(
            self.model_combo,
            self.install_model_button,
            has_models=bool(modes),
        )
        self._apply_app_lock()

    def set_external_gpu_busy(self, busy: bool):
        """Another tool owns the shared infer worker — block Run/Open."""
        self._external_gpu_busy = bool(busy)
        self._apply_app_lock()

    def _apply_app_lock(self):
        installing = self._installing
        processing = self._processing
        external = self._external_gpu_busy
        idle = not installing and not processing and not external
        self.action_bar.set_open_enabled(idle)
        self.action_bar.set_run_enabled(idle and self.model_combo.count() > 0)
        self.action_bar.set_reset_enabled(idle)
        self.action_bar.set_save_enabled(
            idle and self._current_has_unsaved_preview()
        )
        self.action_bar.set_retouch_enabled(
            idle and self._current_has_unsaved_preview()
        )
        self.model_combo.setEnabled(idle and self.model_combo.count() > 0)
        self.install_model_button.setEnabled(idle)
        self.btn_mode_auto.setEnabled(idle)
        self.btn_mode_protect.setEnabled(idle)
        self._update_protect_controls()
        if processing:
            self.action_bar.set_running(True)
        elif not installing:
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
        self.append_output(tr["BgRemove"]["Error"].format(self._format_error_text(message)))
        if self.current_processing_task_index >= 0:
            self.task_list_component.update_task_status(
                self.current_processing_task_index, TaskStatus.FAILED
            )
            # Keep After visible with error hint if we were loading it
            if self.after_view._source is None:
                self.preview.set_after_error(
                    tr["BgRemove"]["Error"].format(self._format_error_text(message))
                )

    def on_task_selected(self, index, path):
        self.current_image_path = path
        self.preview.show_before(path, on_error_hint=tr["BgRemove"]["OpenFailed"].format(path))
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
            self.preview.show_after_loading(tr["BgRemove"]["AfterLoading"])
        else:
            self.preview.hide_after()
        self.action_bar.set_save_enabled(
            not self._processing and not self._installing and self._current_has_unsaved_preview()
        )
        self.action_bar.set_retouch_enabled(
            not self._processing and not self._installing and self._current_has_unsaved_preview()
        )
        self._update_protect_controls()

    def on_task_deleted(self, index, task):
        """Discard temp preview and clean processing / UI state for the removed task."""
        if task is not None:
            _unlink_quiet(getattr(task, "preview_temp_path", None))
            _unlink_quiet(getattr(task, "protect_mask_path", None))

        if self.current_processing_task_index == index:
            self._abort_current_process()
            self.current_processing_task_index = -1
        elif self.current_processing_task_index > index:
            self.current_processing_task_index -= 1

        remaining = len(self.task_list_component.get_all_tasks())
        if remaining == 0:
            self.current_image_path = None
            self.preview.show_empty(tr["BgRemove"].get("SelectImageTitle", tr["BgRemove"]["UploadImage"]))
            self.action_bar.set_save_enabled(False)
            self.action_bar.set_retouch_enabled(False)
            self._update_protect_controls()
            self.append_output(tr["TaskList"]["TaskRemovedEmpty"])
            return

        next_idx = min(index, remaining - 1)
        self.task_list_component.select_task(next_idx)
        self._update_protect_controls()
        self.append_output(tr["TaskList"]["TaskRemoved"].format(task.name if task else ""))

    def _abort_current_process(self):
        """Stop BG remove without confirmation (task was deleted)."""
        self._stop_event.set()
        rid = self._active_run_id
        if rid is not None:
            InferClient.instance().cancel(rid)
        else:
            InferClient.instance().cancel()
        self._active_run_id = None
        self.running_process = None
        self._processing = False
        self._apply_app_lock()
        self.processing_changed.emit(False)

    def open_file(self):
        if self._installing or self._processing:
            return
        diag.upload("Open / Upload image(s)")
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            tr["BgRemove"]["Open"],
            "",
            "Image Files (*.jpg *.jpeg *.png *.bmp *.webp *.tiff *.tif);;All Files (*.*)",
        )
        if files:
            self._open_paths(files)
        else:
            diag.upload("file dialog cancelled")

    def _open_paths(self, files):
        if self._installing or self._processing:
            return
        if not files:
            return
        diag.upload(f"opening {len(files)} path(s)")
        loaded = []
        for path in reversed(list(files)):
            if not is_image_file(path):
                self.append_output(tr["BgRemove"]["ImagesOnly"].format(path))
                continue
            try:
                with Image.open(path) as im:
                    im.verify()
                Image.open(path).close()
            except Exception:
                self.append_output(tr["BgRemove"]["OpenFailed"].format(path))
                continue
            loaded.append(path)
            diag.upload(f"loaded  {path}")
            self.append_output(tr["BgRemove"]["OpenSuccess"].format(path))
        for path in reversed(loaded):
            self.task_list_component.add_task(path, output_suffix="_nobg")
            index = max(0, self.task_list_component.find_task_index_by_path(path))
            self.task_list_component.select_task(index)
        self._update_protect_controls()

    def _on_stop_confirmed(self):
        diag.run("Stop confirmed - aborting BG remove")
        try:
            from backend.tools.diag_health import report_job_state

            report_job_state("on stop")
        except Exception:
            pass
        self._stop_event.set()
        rid = self._active_run_id
        if rid is not None:
            InferClient.instance().cancel(rid)
        else:
            InferClient.instance().cancel()
        self._active_run_id = None
        self.running_process = None
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

    def save_button_clicked(self):
        if self._processing or self._installing:
            return
        diag.save("Save")
        idx = self.task_list_component.get_current_task_index()
        task = self.task_list_component.get_task(idx)
        if not task or not task.preview_temp_path or not os.path.isfile(task.preview_temp_path):
            self.append_output(tr["BgRemove"]["SaveNothing"])
            return

        default_path = task.output_path
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            tr["BgRemove"]["Save"],
            default_path,
            "PNG Image (*.png);;All Files (*.*)",
        )
        if not path:
            diag.save("cancelled")
            self.append_output(tr["BgRemove"]["SaveCancelled"])
            return
        if not path.lower().endswith(".png"):
            path = path + ".png"

        try:
            out_dir = os.path.dirname(os.path.abspath(path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            shutil.copy2(task.preview_temp_path, path)
            task.output_path = path
            task.saved = True
            diag.save(f"ok  {path}")
            self.append_output(tr["BgRemove"]["SaveDone"].format(path))
            self.action_bar.set_save_enabled(True)
            self.action_bar.set_retouch_enabled(True)
        except Exception as e:
            diag.error(f"save failed  {e}")
            self.append_output(tr["BgRemove"]["SaveFailed"].format(str(e)))

    def retouch_button_clicked(self):
        if self._processing or self._installing:
            return
        import time

        diag.event("Retouch dialog requested")
        t0 = time.perf_counter()
        idx = self.task_list_component.get_current_task_index()
        task = self.task_list_component.get_task(idx)
        if not task or not task.preview_temp_path or not os.path.isfile(task.preview_temp_path):
            self.append_output(tr["BgRemove"]["RetouchNothing"])
            return
        try:
            rgba = Image.open(task.preview_temp_path).convert("RGBA")
            rgba.load()
        except Exception as e:
            self.append_output(tr["BgRemove"]["SaveFailed"].format(str(e)))
            return
        t_preview = time.perf_counter()

        original = None
        try:
            if task.path and os.path.isfile(task.path):
                from PIL import ImageOps

                with Image.open(task.path) as im:
                    original = ImageOps.exif_transpose(im).convert("RGBA")
                    original.load()
        except Exception:
            original = None
        t_orig = time.perf_counter()
        diag.event(
            f"Retouch load  preview={rgba.size[0]}x{rgba.size[1]}  "
            f"{(t_preview - t0) * 1000:.0f}ms  "
            f"original={(t_orig - t_preview) * 1000:.0f}ms"
        )

        from ui.bg_retouch_dialog import BgRetouchDialog
        from ui.component.workspace.editor_page import present_editor_dialog

        t_build = time.perf_counter()
        dlg = BgRetouchDialog(rgba, parent=self.window(), original=original)
        diag.event(f"Retouch dialog built  {(time.perf_counter() - t_build) * 1000:.0f}ms")
        mode = present_editor_dialog(dlg, rgba.size)
        diag.event(f"Retouch dialog SHOW  {rgba.size[0]}x{rgba.size[1]}  mode={mode}")

        def on_done(img: Image.Image):
            try:
                img.save(task.preview_temp_path, format="PNG", optimize=True)
                task.saved = False
                self.preview.show_after_rgba(img)
                self.action_bar.set_save_enabled(True)
                self.action_bar.set_retouch_enabled(True)
                self.append_output(tr["BgRetouch"]["LamaDone"])
            except Exception as e:
                self.append_output(tr["BgRemove"]["SaveFailed"].format(str(e)))

        dlg.finished_image.connect(on_done)
        dlg.exec()

    def reset_workspace(self):
        """Clear tasks and discard unsaved temp previews."""
        if self._processing or self._installing:
            return
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        diag.run("Reset workspace")

        removed = self.task_list_component.clear_all()
        for task in removed:
            _unlink_quiet(task.preview_temp_path)
            _unlink_quiet(getattr(task, "protect_mask_path", None))

        self.current_image_path = None
        self.current_processing_task_index = -1
        self.preview.show_empty(tr["BgRemove"].get("SelectImageTitle", tr["BgRemove"]["UploadImage"]))
        self.log_panel.clear()
        self.append_output(tr["BgRemove"]["ResetDone"])
        self.action_bar.set_save_enabled(False)
        self.action_bar.set_retouch_enabled(False)
        self._update_protect_controls()
        try:
            InferClient.instance().request_release()
        except Exception:
            pass
        gc.collect()

    def run_button_clicked(self):
        if self._installing or self._processing or self._external_gpu_busy:
            if self._external_gpu_busy:
                from ui.gpu_busy import gpu_busy_message

                self._show_alert(
                    tr["BgRemove"].get("Title", "Remove BG"),
                    gpu_busy_message(),
                )
            return
        pending = self.task_list_component.get_pending_tasks()
        if not pending:
            # Allow re-run of the selected completed/failed image (e.g. after keep-mask edit)
            cur = self.task_list_component.get_task(
                self.task_list_component.get_current_task_index()
            )
            if cur and self._requeue_task_for_rerun(cur):
                pending = self.task_list_component.get_pending_tasks()
            if not pending:
                if cur:
                    msg = tr["BgRemove"].get(
                        "RerunHint",
                        "This image already ran. Edit keep mask (or right-click → Reset Task), then Run again.",
                    )
                    self.append_output(msg)
                    self._show_alert(
                        tr["BgRemove"].get("RerunHintTitle", tr["TaskList"]["Warning"]),
                        msg,
                    )
                else:
                    self.append_output(tr["BgRemove"]["OpenFirst"])
                return

        modes = selectable_modes()
        if not modes:
            self.append_output(tr["BgRemove"]["NoSelectableModel"])
            return

        mode = self._selected_mode()
        if mode is None or mode not in modes:
            self.append_output(tr["BgRemove"]["NoSelectableModel"])
            return
        # Persist the dropdown selection so config matches what will run
        config.set(config.bgRemoveMode, mode)
        mode_value = mode.value
        protect_mode = self._is_protect_mode()
        diag.run(
            f"BG remove queue  tasks={len(pending)}  model={mode_value}  protect={protect_mode}"
        )
        try:
            from backend.tools.diag_health import report_job_state

            report_job_state("before BG remove run")
        except Exception:
            pass

        # Protect areas requires a painted keep mask before Run / re-run
        if protect_mode:
            _, first_task = pending[0]
            if not self._ensure_protect_mask(first_task):
                self._alert_protect_mask_required()
                return

        self._stop_event.clear()
        self._processing = True
        self._apply_app_lock()
        self.processing_changed.emit(True)

        def task():
            try:
                while not self._stop_event.is_set():
                    pending_tasks = self.task_list_component.get_pending_tasks()
                    if not pending_tasks:
                        break
                    self.current_processing_task_index, task_item = pending_tasks[0]
                    if not is_image_file(task_item.path):
                        self.append_log_signal.emit(
                            [tr["BgRemove"]["ImagesOnly"].format(task_item.path)]
                        )
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.FAILED
                        )
                        continue

                    if protect_mode and not self._ensure_protect_mask(task_item):
                        msg = tr["BgRemove"]["ProtectMaskRequired"]
                        self.append_log_signal.emit([msg])
                        self.alert_signal.emit(
                            tr["BgRemove"]["ProtectMaskRequiredTitle"], msg
                        )
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.FAILED
                        )
                        break

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
                    protect_path = (
                        task_item.protect_mask_path
                        if _task_has_protect_mask(task_item)
                        else None
                    )
                    diag.run(f"processing  {name}  model={mode_value}")
                    diag.process(
                        f"route  BG_REMOVE  in={name}  model={mode_value}  "
                        f"protect={'yes' if protect_path else 'no'}  "
                        f"hw={bool(config.hardwareAcceleration.value)}"
                    )

                    ok = self._run_worker_process(
                        task_item.path,
                        preview_path,
                        mode_value,
                        protect_mask_path=protect_path,
                        display_name=name,
                    )
                    if self._stop_event.is_set():
                        _unlink_quiet(preview_path)
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.STOPPED
                        )
                        self.progress_signal.emit(self.current_processing_task_index, 0)
                        diag.run("stopped by user")
                        break
                    if ok:
                        task_item.preview_temp_path = preview_path
                        self.progress_signal.emit(self.current_processing_task_index, 100)
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.COMPLETED
                        )
                        msgs = [
                            tr["BgRemove"]["Finished"].format(Path(task_item.path).name)
                        ]
                        if protect_path:
                            msgs.append(tr["BgRemove"]["ProtectApplied"])
                        self.append_log_signal.emit(msgs)
                        self.save_enabled_signal.emit(True)
                        diag.run(f"finished  {Path(task_item.path).name}")
                    else:
                        _unlink_quiet(preview_path)
                        self.task_status_signal.emit(
                            self.current_processing_task_index, TaskStatus.FAILED
                        )
                        diag.error(f"failed  {Path(task_item.path).name}")
                        # Don't tight-loop the same pending task if status update is still async.
                        break
            finally:
                self.running_process = None
                self._active_run_id = None
                self.toggle_buttons_signal.emit(True)
                self.current_processing_task_index = -1
                diag.worker("BG remove worker thread exit")

        self._worker_thread = threading.Thread(target=task, daemon=True)
        diag.worker("START  BG remove worker thread")
        self._worker_thread.start()

    def _run_worker_process(
        self,
        input_path: str,
        preview_path: str,
        mode_value: str,
        *,
        protect_mask_path: str | None = None,
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
                self.append_log_signal.emit([
                    tr["BgRemove"]["Processing"].format(name, mode_value, "GPU/CPU")
                ])
            self.progress_signal.emit(task_index, max(1, min(99, int(p))))

        def on_log(msg: str):
            text = str(msg or "")
            lower = text.lower()
            if lower.startswith("queued"):
                # Prefer localized queue line once InferClient reports wait depth.
                pos = "1"
                if "(#" in text and ")" in text:
                    try:
                        pos = text.split("(#", 1)[1].split(")", 1)[0]
                    except Exception:
                        pass
                self.append_log_signal.emit([
                    tr["BgRemove"].get(
                        "Queued",
                        "[Queued] {} - waiting for the current GPU job to finish "
                        "or be stopped. Queue position: {}.",
                    ).format(name, pos)
                ])
                return
            if "worker free" in lower or lower.startswith("starting queued"):
                self.append_log_signal.emit([
                    tr["BgRemove"].get(
                        "QueueStarted",
                        "[Queue] Worker free - starting background removal…",
                    )
                ])
                return
            self.append_log_signal.emit([text])

        def on_error(msg: str):
            if msg == "__cancelled__":
                success["ok"] = False
            elif msg in ("TIMEOUT", "CRASH", "BUSY"):
                success["ok"] = False
                if msg == "BUSY":
                    from ui.gpu_busy import gpu_busy_message

                    text = gpu_busy_message()
                else:
                    text = {
                        "TIMEOUT": "Background removal timed out. The worker was restarted - try again.",
                        "CRASH": "Background removal worker crashed. Try again.",
                    }.get(msg, "Background removal worker crashed. Try again.")
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
            # Keep queued images isolated: unload this run before the next one.
            "release_after_job": True,
        }
        if protect_mask_path:
            payload["protect_mask_path"] = protect_mask_path

        client = InferClient.instance()
        run_id = client.start_job(
            JobType.BG_REMOVE,
            payload,
            on_progress=on_progress,
            on_log=on_log,
            on_result=on_result,
            on_error=on_error,
            on_done=on_done,
            coalesce=False,
        )
        self._active_run_id = run_id if run_id >= 0 else None
        # Wait until job finishes (or stop). Cancel only this run_id so a
        # queued BG job does not kill an active subtitle/video job.
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
        if "rembg" in lower or "not installed" in lower:
            return tr["BgRemove"]["ErrorMissingRembg"]
        if "out of memory" in lower or "vram" in lower or "gpu memory" in lower:
            return (
                "Not enough GPU memory for background removal. "
                "Try a smaller image or close other GPU apps."
            )
        if "cuda" in lower and "memory" in lower:
            return tr["BgRemove"]["ErrorOutOfMemory"]
        return text

    @Slot(list)
    def append_log(self, log):
        self.append_output(*log)

    def append_output(self, *args):
        self.log_panel.append(*args)
