import os
import cv2
import threading
import time
import traceback
from pathlib import Path
from PySide6.QtCore import Slot, Signal
from PySide6.QtWidgets import QWidget
from PySide6 import QtWidgets
from ui.setting_interface import SettingInterface
from ui.component.preview.media_preview_host import MediaPreviewHost, MediaPreviewMode
from ui.component.workspace.task_list_component import TaskStatus, TaskOptions
from ui.component.workspace.action_bar import RailActions
from ui.component.workspace.workspace_page import WorkspacePage
from ui.shell import ContentPage
from backend.config import config, tr
from backend.tools import diag
from backend.tools.constant import InpaintMode
from backend.tools.job_config import snapshot_subtitle_config
from backend.tools.subtitle_remover_remote_call import SubtitleRemoverRemoteCall
from backend.tools.process_manager import ProcessManager
from backend.tools.common_tools import get_readable_path, is_image_file, read_image

class HomeInterface(ContentPage):
    progress_signal = Signal(int, bool)
    append_log_signal = Signal(list)
    update_preview_with_comp_signal = Signal(list)
    task_error_signal = Signal(object)
    toggle_buttons_signal = Signal(bool)  # True=show run button, False=show stop button
    task_status_signal = Signal(int, object)  # (task_index, TaskStatus)
    select_task_signal = Signal(int)  # task_index
    compare_done_signal = Signal(str, str)  # (ok_path_or_empty, error_or_empty)
    def __init__(self, parent=None):
        super().__init__("HomeInterface", parent=parent)
        # Initialize variables
        self.video_path = None
        self.video_cap = None
        self.fps = None
        self.frame_count = None
        self.frame_width = None
        self.frame_height = None
        self.se = None  # Background subtitle extractor

        # Subtitle region parameters
        self.xmin = None
        self.xmax = None
        self.ymin = None
        self.ymax = None

        # Auto-scroll control flag (owned by LogPanel; kept for compatibility)
        self._stop_event = threading.Event()  # Thread-safe stop signal
        self._worker_thread = None
        self.running_process = None
        self._saved_inpaint_mode = None  # Inpaint mode before image-mode lock
        self._video_cap_lock = threading.Lock()  # Lock protecting video_cap

        # Index of the task currently being processed
        self.current_processing_task_index = -1
        self._active_run_id: int | None = None
        self._compare_thread: threading.Thread | None = None

        self.__init_widgets()
        self.progress_signal.connect(self.update_progress)
        self.append_log_signal.connect(self.append_log)
        self.update_preview_with_comp_signal.connect(self.update_preview_with_comp)
        self.task_error_signal.connect(self.on_task_error)
        self.toggle_buttons_signal.connect(self._toggle_buttons)
        self.task_status_signal.connect(self._on_task_status)
        self.select_task_signal.connect(self.task_list_component.select_task)
        self.compare_done_signal.connect(self._on_compare_done)
        self.append_output(tr['SubtitleExtractorGUI']['EmptyStateHint'])

    def __init_widgets(self):
        """Create the home page"""
        self.media_preview = MediaPreviewHost(self)
        self.video_display_component = self.media_preview.video_display
        self.video_display_component.ab_sections_changed.connect(self.ab_sections_changed)
        self.video_display_component.selections_changed.connect(self.selections_changed)
        self.media_preview.before_view.selections_changed.connect(self.selections_changed)
        self.video_display = self.video_display_component.video_display
        self.video_slider = self.media_preview.video_slider
        self.video_slider.valueChanged.connect(self.slider_changed)
        self.media_preview.empty_clicked.connect(self.open_file)
        self.media_preview.files_dropped.connect(self._open_paths)

        settings_host = QWidget(self)
        self.setting_interface = SettingInterface(settings_host)
        settings_host.setLayout(self.setting_interface)

        gui = tr["SubtitleExtractorGUI"]
        self.workspace = WorkspacePage(
            preview=self.media_preview,
            settings=settings_host,
            actions=RailActions(
                open_text=gui["Open"],
                run_text=gui["Run"],
                stop_text=gui["Stop"],
                stop_confirm_title=gui["StopConfirmTitle"],
                stop_confirm_desc=gui["StopConfirmDesc"],
                reset_text=gui["Reset"],
                reset_confirm_title=gui["ResetConfirmTitle"],
                reset_confirm_desc=gui["ResetConfirmDesc"],
                empty_list_hint=tr["TaskList"]["EmptyListHint"],
                settings_title=gui["Setting"],
                compare_text=gui.get("Compare", "Compare"),
            ),
            parent=self,
            preview_title=gui.get("VideoPreview", "Preview"),
            preview_bordered=True,
        )
        self.log_panel = self.workspace.log_panel
        self.task_list_component = self.workspace.task_list_component
        self.action_bar = self.workspace.action_bar
        self.action_bar.open_clicked.connect(self.open_file)
        self.action_bar.run_clicked.connect(self.run_button_clicked)
        self.action_bar.stop_confirmed.connect(self._on_stop_confirmed)
        self.action_bar.reset_confirmed.connect(self.reset_workspace)
        self.action_bar.compare_clicked.connect(self.compare_button_clicked)
        self.task_list_component.task_selected.connect(self.on_task_selected)
        self.task_list_component.task_deleted.connect(self.on_task_deleted)

        self.body.addWidget(self.workspace)
    
    def on_scroll_change(self, value):
        """Deprecated: LogPanel owns scroll behavior."""
        pass

    
    def slider_changed(self, value):
        if self.media_preview.mode != MediaPreviewMode.VIDEO:
            return
        frame = None
        with self._video_cap_lock:
            if self.video_cap is not None and self.video_cap.isOpened():
                frame_no = self.video_slider.value()
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                ret, frame = self.video_cap.read()
                if not ret:
                    frame = None
        if frame is not None:
            # Update preview image
            self.update_preview(frame)

    def ab_sections_changed(self, ab_sections):
        get_current_task_index = self.task_list_component.get_current_task_index()
        if get_current_task_index == -1:
            return
        self.task_list_component.update_task_option(get_current_task_index, TaskOptions.AB_SECTIONS, ab_sections)

    def selections_changed(self, selections):
        get_current_task_index = self.task_list_component.get_current_task_index()
        if get_current_task_index == -1:
            return
        self.task_list_component.update_task_option(get_current_task_index, TaskOptions.SUB_AREAS, selections)

    def _on_task_status(self, idx, status):
        self.task_list_component.update_task_status(idx, status)
        self._update_compare_enabled()
        if idx != self.task_list_component.get_current_task_index():
            return
        if self.media_preview.mode != MediaPreviewMode.IMAGE:
            return
        if status == TaskStatus.PROCESSING:
            self.media_preview.show_after_loading()
        elif status == TaskStatus.COMPLETED:
            task = self.task_list_component.get_task(idx)
            if task:
                self.media_preview.show_image(task.path)
                selections = self.task_list_component.get_task_option(idx, TaskOptions.SUB_AREAS, [])
                if selections:
                    self.media_preview.before_view.set_selection_rects(selections)
            self._refresh_image_after(idx)
        elif status in (TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.STOPPED):
            task = self.task_list_component.get_task(idx)
            out = getattr(task, "output_path", None) if task else None
            if out and os.path.isfile(out):
                self.media_preview.show_after_path(out)
            else:
                self.media_preview.hide_after()

    def _refresh_image_after(self, index: int):
        task = self.task_list_component.get_task(index)
        if not task:
            self.media_preview.hide_after()
            return
        out = task.output_path
        if out and os.path.isfile(out):
            self.media_preview.show_after_path(out)
        else:
            self.media_preview.hide_after()

    def on_task_selected(self, index, file_path):
        """Handle task selected event
        
        Args:
            index: task index
            file_path: file path
        """
        self.video_display_component.pause()
        # Load selected video/image for preview
        self.load_video(file_path)

        if self.media_preview.mode == MediaPreviewMode.IMAGE:
            selections = self.task_list_component.get_task_option(index, TaskOptions.SUB_AREAS, [])
            self.media_preview.before_view.set_selection_rects(selections or [])
            task = self.task_list_component.get_task(index)
            if (
                task
                and task.status == TaskStatus.PROCESSING
                and index == self.current_processing_task_index
            ):
                self.media_preview.show_after_loading()
            elif task and task.status == TaskStatus.COMPLETED:
                self._refresh_image_after(index)
            else:
                out = task.output_path if task else None
                if out and os.path.isfile(out):
                    self.media_preview.show_after_path(out)
                else:
                    self.media_preview.hide_after()
            self._update_compare_enabled()
            return

        ab_sections = self.task_list_component.get_task_option(index, TaskOptions.AB_SECTIONS, [])
        self.video_display_component.set_ab_sections(ab_sections)
        selections = self.task_list_component.get_task_option(index, TaskOptions.SUB_AREAS, [])
        if len(selections) <= 0:
            self.video_display_component.load_selections_from_config()
        else:
            self.video_display_component.set_selection_rects(selections)
        self._update_compare_enabled()

    def on_task_deleted(self, index, task):
        """Clean preview / processing state after a task is removed."""
        # Adjust or abort in-flight processing
        if self.current_processing_task_index == index:
            self._abort_current_process()
            self.current_processing_task_index = -1
        elif self.current_processing_task_index > index:
            self.current_processing_task_index -= 1

        remaining = len(self.task_list_component.get_all_tasks())
        if remaining == 0:
            with self._video_cap_lock:
                if self.video_cap is not None:
                    self.video_cap.release()
                    self.video_cap = None
            self.video_path = None
            self.fps = None
            self.frame_count = None
            self.frame_width = None
            self.frame_height = None
            self._unlock_inpaint_mode()
            self.media_preview.show_empty()
            self.video_slider.setMaximum(1)
            self.video_slider.setValue(1)
            self.append_output(tr['TaskList']['TaskRemovedEmpty'])
            self._update_compare_enabled()
            return

        # Keep a valid selection / preview
        next_idx = min(index, remaining - 1)
        self.task_list_component.select_task(next_idx)
        self.append_output(tr['TaskList']['TaskRemoved'].format(task.name if task else ""))
        self._update_compare_enabled()

    def _stop_infer_job(self):
        """Hard-cancel this page's infer job (or unqueue it) without touching others' wait slots."""
        try:
            from backend.tools.infer_client import InferClient

            rid = self._active_run_id
            if rid is not None:
                InferClient.instance().cancel(rid)
            else:
                InferClient.instance().cancel()
            self._active_run_id = None
        except Exception:
            pass
        running_process = self.running_process
        if running_process is not None and running_process != "infer-client":
            try:
                ProcessManager.instance().terminate_by_process(running_process)
            except Exception:
                pass

    def _abort_current_process(self):
        """Stop the running remover without confirmation (task was deleted)."""
        try:
            self._stop_event.set()
            self._stop_infer_job()
        finally:
            self.running_process = None
            self.action_bar.set_running(False)
            self._update_compare_enabled()

    def update_preview(self, frame):
        # Scale the image first
        resized_frame = self._img_resize(frame)

        # Set video parameters
        self.video_display_component.set_video_parameters(
            self.frame_width, self.frame_height, 
            self.scaled_width if hasattr(self, 'scaled_width') else None,
            self.scaled_height if hasattr(self, 'scaled_height') else None,
            self.border_left if hasattr(self, 'border_left') else 0,
            self.border_top if hasattr(self, 'border_top') else 0,
            self.fps if self.fps is not None else 30,
        )
        
        # Update video display (also saves current_pixmap)
        self.video_display_component.update_video_display(resized_frame)

    def _img_resize(self, image):
        height, width = image.shape[:2]
        
        video_preview_width = self.video_display_component.video_preview_width
        video_preview_height = self.video_display_component.video_preview_height
        # Compute aspect-ratio-preserving size
        target_ratio = video_preview_width / video_preview_height
        image_ratio = width / height
        
        if image_ratio > target_ratio:
            # Fit width, scale height proportionally
            new_width = video_preview_width
            new_height = int(new_width / image_ratio)
            top_border = (video_preview_height - new_height) // 2
            bottom_border = video_preview_height - new_height - top_border
            left_border = 0
            right_border = 0
        else:
            # Fit height, scale width proportionally
            new_height = video_preview_height
            new_width = int(new_height * image_ratio)
            left_border = (video_preview_width - new_width) // 2
            right_border = video_preview_width - new_width - left_border
            top_border = 0
            bottom_border = 0
        
        # Scale the image first
        resized = cv2.resize(image, (new_width, new_height))
        
        # Add black bars to fill target size
        padded = cv2.copyMakeBorder(
            resized, 
            top_border, bottom_border, 
            left_border, right_border, 
            cv2.BORDER_CONSTANT, 
            value=[0, 0, 0]
        )
        
        # Save border info for coordinate conversion
        self.border_left = left_border / video_preview_width
        self.border_right = right_border / video_preview_width
        self.border_top = top_border / video_preview_height
        self.border_bottom = bottom_border / video_preview_height
        self.original_width = width
        self.original_height = height
        self.is_vertical = width < height
        self.scaled_width = new_width / video_preview_width
        self.scaled_height = new_height / video_preview_height
        
        return padded

    def _on_stop_confirmed(self):
        try:
            self._stop_event.set()
            self._stop_infer_job()
            if self.current_processing_task_index >= 0:
                self.task_list_component.update_task_status(
                    self.current_processing_task_index, TaskStatus.STOPPED
                )
                self.task_list_component.update_task_progress(
                    self.current_processing_task_index, 0
                )
                if self.media_preview.mode == MediaPreviewMode.IMAGE:
                    self.media_preview.hide_after()
        finally:
            self.running_process = None
            self.action_bar.set_running(False)
            self._update_compare_enabled()

    def reset_workspace(self):
        """Clear tasks and release video/memory - keep files on disk."""
        import gc

        if self.running_process is not None or (
            self._worker_thread is not None and self._worker_thread.is_alive()
        ):
            return
        if self._compare_thread is not None and self._compare_thread.is_alive():
            return

        self.task_list_component.clear_all()

        with self._video_cap_lock:
            if self.video_cap is not None:
                self.video_cap.release()
                self.video_cap = None

        self.video_path = None
        self.fps = None
        self.frame_count = None
        self.frame_width = None
        self.frame_height = None
        self.current_processing_task_index = -1
        self.se = None
        self._unlock_inpaint_mode()

        self.media_preview.show_empty()
        self.video_slider.setMaximum(1)
        self.video_slider.setValue(1)
        self.log_panel.clear()
        self.append_output(tr['SubtitleExtractorGUI']['ResetDone'])
        try:
            from backend.tools.infer_client import InferClient

            InferClient.instance().request_release()
        except Exception:
            pass
        self._update_compare_enabled()
        gc.collect()

    @Slot(bool)
    def _toggle_buttons(self, show_run):
        """Toggle button visibility thread-safely (show_run=True => idle)."""
        self.action_bar.set_running(not show_run)
        self._update_compare_enabled()

    def _can_compare_current_task(self) -> bool:
        if self.running_process is not None:
            return False
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return False
        if self._compare_thread is not None and self._compare_thread.is_alive():
            return False
        idx = self.task_list_component.get_current_task_index()
        task = self.task_list_component.get_task(idx)
        if task is None or task.status != TaskStatus.COMPLETED:
            return False
        if is_image_file(task.path):
            return False
        if not task.path or not os.path.isfile(task.path):
            return False
        out = task.output_path
        return bool(out and os.path.isfile(out))

    def _update_compare_enabled(self):
        self.action_bar.set_compare_enabled(self._can_compare_current_task())

    def compare_button_clicked(self):
        gui = tr["SubtitleExtractorGUI"]
        if self._compare_thread is not None and self._compare_thread.is_alive():
            self.append_output(gui.get("CompareBusy", "Compare is already running."))
            return
        if not self._can_compare_current_task():
            self.append_output(gui.get("CompareNothing", "Nothing to compare."))
            return

        idx = self.task_list_component.get_current_task_index()
        task = self.task_list_component.get_task(idx)
        src = task.path
        cleaned = task.output_path
        out_dir = os.path.dirname(os.path.abspath(cleaned)) or "."
        out_path = os.path.join(out_dir, f"{Path(cleaned).stem}_compare.mp4")

        self.append_output(gui.get("CompareStart", "[Compare] Building side-by-side video…"))
        self.action_bar.set_compare_enabled(False)

        def work():
            try:
                from backend.tools.merge_video import merge_video

                path = merge_video(src, cleaned, out_path, layout="horizontal")
                self.compare_done_signal.emit(path, "")
            except Exception as e:
                traceback.print_exc()
                self.compare_done_signal.emit("", str(e))

        self._compare_thread = threading.Thread(target=work, daemon=True, name="compare-merge")
        self._compare_thread.start()

    @Slot(str, str)
    def _on_compare_done(self, path: str, error: str):
        gui = tr["SubtitleExtractorGUI"]
        if error:
            self.append_output(gui.get("CompareFailed", "[Compare] Failed: {}").format(error))
        elif path:
            self.append_output(gui.get("CompareDone", "[Compare] Side-by-side video saved to: {}").format(path))
        self._update_compare_enabled()

    def run_button_clicked(self):
        diag.run("subtitle / inpaint queue")
        if not self.task_list_component.get_pending_tasks():
            self.append_output(tr['SubtitleExtractorGUI']['OpenVideoFirst'])
            return

        try:
            # Get all pending tasks
            pending_tasks = self.task_list_component.get_pending_tasks()
            if not pending_tasks:
                return

            diag.run(f"subtitle queue  tasks={len(pending_tasks)}")
            self._stop_event.clear()
            self.toggle_buttons_signal.emit(False)
            # Start background thread to process video
            def task():
                try:
                    while not self._stop_event.is_set():
                        try:
                            pending_tasks = self.task_list_component.get_pending_tasks()
                            if not pending_tasks:
                                break
                            pending_task = pending_tasks[0]
                            # Update current processing task index
                            self.current_processing_task_index, task_item = pending_task
                            diag.run(f"processing  {task_item.path}")
                            if not self.load_video(task_item.path):
                                self.append_log_signal.emit([tr['SubtitleExtractorGUI']['OpenVideoFailed'].format(task_item.path)])
                                self.task_status_signal.emit(self.current_processing_task_index, TaskStatus.FAILED)
                                continue

                            # Get subtitle region coords; use full frame if none selected
                            subtitle_areas = self.task_list_component.get_task_option(self.current_processing_task_index, TaskOptions.SUB_AREAS, [])
                            is_image = is_image_file(task_item.path)
                            if (not subtitle_areas or len(subtitle_areas) <= 0) and not is_image:
                                # Video display stores preview ratios; seed full-frame pixels only for video path compat
                                subtitle_areas = [(0, self.frame_height, 0, self.frame_width)]
                                self.task_list_component.update_task_option(self.current_processing_task_index, TaskOptions.SUB_AREAS, subtitle_areas)

                            if not is_image:
                                self.video_display_component.save_selections_to_config()

                            # Update task status to processing
                            self.task_list_component.update_task_progress(self.current_processing_task_index, 1)

                            # Select current task
                            self.select_task_signal.emit(self.current_processing_task_index)

                            with self._video_cap_lock:
                                if self.video_cap:
                                    self.video_cap.release()
                                    self.video_cap = None

                            self.task_status_signal.emit(self.current_processing_task_index, TaskStatus.PROCESSING)
                            options = {}
                            for key in task_item.options:
                                value = task_item.options[key]
                                if key == TaskOptions.SUB_AREAS.value:
                                    if is_image:
                                        # Ratio rects from ZoomableImageView → pixels
                                        value = self.media_preview.before_view.ratios_to_pixels(
                                            self.frame_width, self.frame_height
                                        )
                                        if not value:
                                            value = [(0, self.frame_height, 0, self.frame_width)]
                                    else:
                                        value = self.video_display_component.preview_coordinates_to_video_coordinates(value)
                                options[key] = value
                            # Clear cache, use dynamic path
                            task_item.output_path = None
                            output_path = task_item.output_path
                            process = self.run_subtitle_remover_process(task_item.path, output_path, options)

                            # Check if stopped during processing
                            if self._stop_event.is_set():
                                self.task_status_signal.emit(
                                    self.current_processing_task_index, TaskStatus.STOPPED
                                )
                                self.progress_signal.emit(0, True)
                                break

                            # Update task status to completed
                            task_obj = self.task_list_component.get_task(self.current_processing_task_index)
                            if process.exitcode == 0 and task_obj and task_obj.status == TaskStatus.PROCESSING:
                                self.progress_signal.emit(100, True)
                                # Task done; set output path as read-only
                                task_obj.output_path = output_path
                                self.task_status_signal.emit(self.current_processing_task_index, TaskStatus.COMPLETED)
                            else:
                                self.task_status_signal.emit(self.current_processing_task_index, TaskStatus.FAILED)

                        except Exception as e:
                            print(e)
                            self.append_log_signal.emit([f"Error: {e}"])
                            # Update task status to failed
                            if self.current_processing_task_index >= 0:
                                self.task_status_signal.emit(self.current_processing_task_index, TaskStatus.FAILED)
                            break
                        finally:
                            with self._video_cap_lock:
                                if self.video_cap:
                                    self.video_cap.release()
                                    self.video_cap = None
                            time.sleep(1)
                finally:
                    self.toggle_buttons_signal.emit(True)
                    diag.worker("subtitle worker thread exit")

            self._worker_thread = threading.Thread(target=task, daemon=True)
            diag.worker("START  subtitle worker thread")
            self._worker_thread.start()
        except Exception as e:
            print(traceback.format_exc())
            self.append_log_signal.emit([f"Error: {e}"])
            self.toggle_buttons_signal.emit(True)

    @staticmethod
    def remover_process(queue, video_path, output_path, options):
        """Legacy entry kept for compatibility; prefer InferClient subtitle jobs."""
        sr = None
        try:
            from backend.main import SubtitleRemover
            sr = SubtitleRemover(video_path, True)
            sr.video_out_path = output_path
            for key in options:
                setattr(sr, key, options[key])
            sr.add_progress_listener(lambda progress, isFinished: SubtitleRemoverRemoteCall.remote_call_update_progress(queue, progress, isFinished))
            sr.append_output = lambda *args: SubtitleRemoverRemoteCall.remote_call_append_log(queue, args)
            sr.manage_process = lambda pid: SubtitleRemoverRemoteCall.remote_call_manage_process(queue, pid)
            sr.update_preview_with_comp = lambda *args: SubtitleRemoverRemoteCall.remote_call_update_preview_with_comp(queue, args)
            sr.run()
        except Exception as e:
            traceback.print_exc()
            SubtitleRemoverRemoteCall.remote_call_catch_error(queue, e)
        finally:
            if sr:
                sr.isFinished = True
                sr.vsf_running = False
            SubtitleRemoverRemoteCall.remote_call_finish(queue)

    # run_subtitle_remover_process method
    def run_subtitle_remover_process(self, video_path, output_path, options):
        """
        Run subtitle removal via the shared InferClient worker and wait until done.
        If another GPU job is active, this job waits in the shared FIFO queue.
        """
        from backend.tools.infer_client import InferClient
        from backend.tools.infer_protocol import JobType

        done = threading.Event()
        result_box = {"ok": True, "exitcode": 0}
        name = Path(video_path).name if video_path else "media"

        def on_progress(p: int):
            # SubtitleRemover historically sent (progress, isFinished)
            self.progress_signal.emit(int(p), False)

        def on_log(msg: str):
            text = str(msg or "")
            lower = text.lower()
            if lower.startswith("queued"):
                pos = "1"
                if "(#" in text and ")" in text:
                    try:
                        pos = text.split("(#", 1)[1].split(")", 1)[0]
                    except Exception:
                        pass
                self.append_log_signal.emit([
                    tr["SubtitleExtractorGUI"].get(
                        "Queued",
                        "[Queued] {} - waiting for the current GPU job to finish "
                        "or be stopped. Queue position: {}.",
                    ).format(name, pos)
                ])
                return
            if "worker free" in lower or lower.startswith("starting queued"):
                self.append_log_signal.emit([
                    tr["SubtitleExtractorGUI"].get(
                        "QueueStarted",
                        "[Queue] Worker free - starting subtitle removal…",
                    )
                ])
                return
            self.append_log_signal.emit([text])

        def on_preview(**kwargs):
            args = kwargs.get("args")
            if args is not None:
                self.update_preview_with_comp_signal.emit(list(args) if not isinstance(args, list) else args)

        def on_error(msg: str):
            result_box["ok"] = False
            result_box["exitcode"] = 1
            if msg not in ("__cancelled__",):
                self.task_error_signal.emit(msg)
            done.set()

        def on_result(path: str):
            self.progress_signal.emit(100, True)
            done.set()

        def on_done():
            done.set()

        if self._stop_event.is_set():
            return None

        client = InferClient.instance()
        run_id = client.start_job(
            JobType.SUBTITLE,
            {
                "video_path": video_path,
                "output_path": output_path,
                "options": options,
                "config": snapshot_subtitle_config(),
            },
            on_progress=on_progress,
            on_log=on_log,
            on_result=on_result,
            on_error=on_error,
            on_preview=on_preview,
            on_done=on_done,
            coalesce=False,
        )
        self._active_run_id = run_id if run_id >= 0 else None
        self.running_process = "infer-client"

        while not done.wait(timeout=0.25):
            if self._stop_event.is_set():
                if self._active_run_id is not None:
                    client.cancel(self._active_run_id)
                else:
                    client.cancel()
                result_box["ok"] = False
                result_box["exitcode"] = -1
                break

        self._active_run_id = None
        self.running_process = None

        class _ProcProxy:
            exitcode = result_box["exitcode"]

        print(f"Infer subtitle job finished exitcode={result_box['exitcode']}")
        return _ProcProxy()

    @Slot()
    def processing_finished(self):
        pending_tasks = self.task_list_component.get_pending_tasks()
        if pending_tasks:
            # Pending tasks remain; ignore
            return
        # Restore UI availability after processing
        self.action_bar.set_running(False)
        self.se = None
        # Reset video slider
        self.video_slider.setValue(1)
        # Reset current processing task index
        self.current_processing_task_index = -1
        self._update_compare_enabled()

    @Slot(int, bool)
    def update_progress(self, progress_total, isFinished):
        try:
            self.video_display_component.pause()
            pos = min(self.frame_count - 1, int(progress_total / 100 * self.frame_count))
            if pos != self.video_slider.value():
                self.video_slider.blockSignals(True)
                self.video_slider.setValue(pos)
                self.video_slider.blockSignals(False)
            
            # Update task progress
            if self.current_processing_task_index >= 0:
                self.task_list_component.update_task_progress(
                    self.current_processing_task_index, 
                    progress_total,
                )
            
            # Check if finished
            if isFinished:
                diag.run("subtitle task finished")
                self.processing_finished()
        except Exception as e:
            # Catch any exception to prevent crash
            print(f"Error updating progress: {str(e)}")

    @Slot(list)
    def append_log(self, log):
        self.append_output(*log)

    def append_output(self, *args):
        """Append text to the shared log panel."""
        self.log_panel.append(*args)

    @Slot(list)
    def update_preview_with_comp(self, args):
        """Update preview during processing"""
        self.video_display_component.pause()
        frame_ori, frame_comp = args
        # Image mode: After pane shows the cleaned frame; Before stays the source
        if self.media_preview.mode == MediaPreviewMode.IMAGE:
            try:
                rgb = cv2.cvtColor(frame_comp, cv2.COLOR_BGR2RGB)
                from PySide6.QtGui import QImage, QPixmap
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                self.media_preview.after_view.set_pixmap(QPixmap.fromImage(qimg.copy()), fit=True)
            except Exception:
                self.media_preview.show_after_loading()
            return

        if self.current_processing_task_index >= 0:
            subtitle_areas = self.task_list_component.get_task_option(self.current_processing_task_index, TaskOptions.SUB_AREAS, [])
            if len(subtitle_areas) > 0:
                subtitle_areas = self.video_display_component.preview_coordinates_to_video_coordinates(subtitle_areas)
                if frame_ori is frame_comp:
                    frame_ori = frame_ori.copy()
                for rect in subtitle_areas:
                    ymin, ymax, xmin, xmax = rect
                    cv2.rectangle(frame_ori, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
        preview_frame = cv2.hconcat([frame_ori, frame_comp])
        # Scale the image first
        resized_frame = self._img_resize(preview_frame)
        # Update video display (also saves current_pixmap)
        self.video_display_component.update_video_display(resized_frame, draw_selection=False)
        self.video_display_component.set_dragger_enabled(False)

    @Slot(object)
    def on_task_error(self, e):
        self.append_output(tr['SubtitleExtractorGUI']['ErrorDuringProcessing'].format(self._format_task_error(e)))
        if self.current_processing_task_index >= 0:
            self.task_list_component.update_task_status(self.current_processing_task_index, TaskStatus.FAILED)

    def _format_task_error(self, e) -> str:
        """Map common failures to clearer user-facing messages."""
        if self._stop_event.is_set():
            return tr['SubtitleExtractorGUI']['ErrorCancelled']
        text = str(e) if e is not None else ''
        lower = text.lower()
        if isinstance(e, MemoryError) or 'out of memory' in lower or ('cuda' in lower and 'memory' in lower) or 'cudnn_status_alloc_failed' in lower:
            return tr['SubtitleExtractorGUI']['ErrorOutOfMemory']
        if 'codec' in lower or 'could not open' in lower or 'invalid data' in lower or 'unsupported' in lower:
            return tr['SubtitleExtractorGUI']['ErrorUnsupportedCodec']
        if 'cancel' in lower or 'interrupted' in lower:
            return tr['SubtitleExtractorGUI']['ErrorCancelled']
        return text or repr(e)

    def load_video(self, video_path):
        self.video_path = video_path
        self.video_display_component.pause()
        with self._video_cap_lock:
            if self.video_cap:
                self.video_cap.release()
                self.video_cap = None
        # If image file, load as picture
        if is_image_file(video_path):
            return self.load_as_picture(video_path)
        with self._video_cap_lock:
            self.video_cap = cv2.VideoCapture(get_readable_path(self.video_path))
            if not self.video_cap.isOpened():
                self.video_cap = None
                return self.load_as_picture(video_path)
            ret, frame = self.video_cap.read()
            if not ret:
                self.video_cap.release()
                self.video_cap = None
                return self.load_as_picture(video_path)
            self.frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.frame_height = int(self.video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.frame_width = int(self.video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.fps = self.video_cap.get(cv2.CAP_PROP_FPS)

        self.media_preview.show_video()
        self.update_preview(frame)
        self.video_slider.setMaximum(self.frame_count)
        self.video_slider.setValue(1)
        self.video_display_component.set_dragger_enabled(True)
        # In video mode, restore the user's original inpaint mode
        self._unlock_inpaint_mode()
        return True

    def load_as_picture(self, path):
        if not is_image_file(path):
            return False
        self.video_path = path
        self.video_cap = None
        frame = read_image(get_readable_path(path))
        if frame is None:
            return False
        self.frame_count = 1
        self.frame_height = frame.shape[0]
        self.frame_width = frame.shape[1]
        self.fps = 1
        self.media_preview.show_image(path)
        self.media_preview.hide_after()
        # Lock to LAMA in image mode
        self._lock_inpaint_mode_to_lama()
        return True

    def _lock_inpaint_mode_to_lama(self):
        """Lock inpaint mode to LAMA for image mode"""
        if self._saved_inpaint_mode is None:
            self._saved_inpaint_mode = config.inpaintMode.value
        config.set(config.inpaintMode, InpaintMode.LAMA)
        self.setting_interface.set_inpaint_mode_enabled(False)

    def _unlock_inpaint_mode(self):
        """Restore the user's original inpaint mode for video mode"""
        if self._saved_inpaint_mode is not None:
            config.set(config.inpaintMode, self._saved_inpaint_mode)
            self._saved_inpaint_mode = None
        self.setting_interface.set_inpaint_mode_enabled(True)
        self.video_slider.setValue(1)
        self.video_display_component.set_dragger_enabled(True)
        return True


    def open_file(self):
        diag.upload("Open / Upload video or image")
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            tr['SubtitleExtractorGUI']['Open'],
            "",
            "All Files (*.*);;Video Files (*.mp4 *.flv *.wmv *.avi *.mkv *.mov);;Image Files (*.jpg *.jpeg *.png *.bmp *.webp *.tiff)"
        )
        if files:
            self._open_paths(files)
        else:
            diag.upload("file dialog cancelled")

    def _open_paths(self, files):
        if not files:
            return
        diag.upload(f"opening {len(files)} path(s)")
        files_loaded = []
        for path in reversed(list(files)):
            if self.load_video(path):
                diag.upload(f"loaded  {path}")
                self.append_output(f"{tr['SubtitleExtractorGUI']['OpenVideoSuccess']}: {path}")
                files_loaded.append(path)
            else:
                self.append_output(f"{tr['SubtitleExtractorGUI']['OpenVideoFailed']}: {path}")
        for path in reversed(files_loaded):
            self.task_list_component.add_task(path)
            index = max(0, self.task_list_component.find_task_index_by_path(path))
            self.task_list_component.select_task(index)

    def closeEvent(self, event):
        """Disconnect signals and clean up resources on close"""
        try:
            # Signal worker thread to stop
            self._stop_event.set()
            # Terminate child processes
            ProcessManager.instance().terminate_all()
            # Wait for worker thread to finish (up to 5s)
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=5)

            # Disconnect signals
            self.progress_signal.disconnect(self.update_progress)
            self.append_log_signal.disconnect(self.append_log)
            self.update_preview_with_comp_signal.disconnect(self.update_preview_with_comp)
            self.task_error_signal.disconnect(self.on_task_error)
            self.toggle_buttons_signal.disconnect(self._toggle_buttons)
            self.video_display_component.video_slider.valueChanged.disconnect(self.slider_changed)
            self.video_display_component.ab_sections_changed.disconnect(self.ab_sections_changed)
            self.video_display_component.selections_changed.disconnect(self.selections_changed)
            # Release video resources
            with self._video_cap_lock:
                if self.video_cap:
                    self.video_cap.release()
                    self.video_cap = None
        except Exception as e:
            print(f"Error during close window:", e)
        super().closeEvent(event)
    