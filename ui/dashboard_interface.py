"""ChatGPT-style home dashboard: greeting, PC info, prompt → Generate (FLUX.2)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    PlainTextEdit,
    SubtitleLabel,
    TitleLabel,
)

from backend.config import config, tr
from backend.tools.constant import GenerateMode
from backend.tools.generate_models import (
    cuda_ready_for_generate,
    ensure_selected_mode_valid,
    selectable_modes,
)
from backend.tools.infer_client import InferClient
from backend.tools.infer_protocol import JobType
from backend.tools.system_info import collect_system_info, greeting_for_now
from ui.component.cards.info_setting_card import InfoSettingCard
from ui.component.cards.setting_card_style import apply_content_column_width
from ui.component.controls.button_styles import make_button
from ui.theme import HOME, PRIMARY, apply_page_bg

# Content column stretch from SETTINGS content_ratio (~80% → 1:8:1)
_COLUMN_STRETCH = 8
_SIDE_STRETCH = 1
_PREVIEW_MAX = 320


class _PromptBox(QWidget):
    submitted = Signal(str)
    attach_clicked = Signal()
    stop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input = None
        self.setObjectName("PromptBox")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(HOME["gap"])

        hd = tr["HomeDashboard"]
        self.input = PlainTextEdit(self)
        self.input.setPlaceholderText(hd["PromptPlaceholder"])
        self.input.setFixedHeight(HOME["prompt_h"])
        self.input.setTabChangesFocus(True)
        self.input.installEventFilter(self)
        root.addWidget(self.input)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(HOME["gap"])

        self.attach_btn = make_button(hd["Attach"], "secondary", self, FluentIcon.FOLDER)
        self.attach_btn.clicked.connect(self.attach_clicked.emit)
        row.addWidget(self.attach_btn)
        row.addStretch(1)

        self.stop_btn = make_button(
            hd.get("StopGenerate", "Stop"), "secondary", self, FluentIcon.CANCEL
        )
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        self.stop_btn.hide()
        row.addWidget(self.stop_btn)

        self.generate_btn = make_button(
            hd.get("Generate", "Generate"), "primary", self, FluentIcon.EDIT
        )
        self.generate_btn.clicked.connect(self._submit)
        row.addWidget(self.generate_btn)
        root.addLayout(row)

    def _submit(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)

    def set_generating(self, busy: bool):
        self.generate_btn.setVisible(not busy)
        self.stop_btn.setVisible(busy)
        self.input.setReadOnly(busy)
        self.attach_btn.setEnabled(not busy)

    def set_generate_enabled(self, enabled: bool, tooltip: str = ""):
        self.generate_btn.setEnabled(enabled)
        self.generate_btn.setToolTip(tooltip or "")

    def eventFilter(self, obj, event):
        inp = getattr(self, "input", None)
        if inp is not None and obj is inp and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False
                if self.generate_btn.isEnabled() and self.generate_btn.isVisible():
                    self._submit()
                return True
        return super().eventFilter(obj, event)


class DashboardInterface(QWidget):
    """Landing home - greeting, system SettingCards, prompt → Generate."""

    open_bg_remove = Signal()
    open_upscale = Signal()
    open_low_light = Signal()
    open_video = Signal()
    open_settings = Signal()
    open_files = Signal()
    processing_changed = Signal(bool)

    # Worker-thread → GUI
    _progress_signal = Signal(int)
    _error_signal = Signal(str)
    _result_signal = Signal(str)
    _done_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("DashboardInterface")
        self._info = collect_system_info()
        self._active_run_id: int | None = None
        self._last_result_path: str | None = None
        self._cuda_ok = False
        self._cuda_reason = ""
        self._external_gpu_busy = False
        self._build()
        self._progress_signal.connect(self._on_progress_ui)
        self._error_signal.connect(self._on_error_ui)
        self._result_signal.connect(self._on_result_ui)
        self._done_signal.connect(self._on_done_ui)
        self.refresh_generate_gate()

    def _build(self):
        hd = tr["HomeDashboard"]
        scroll = QScrollArea(self)
        scroll.setObjectName("DashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        page = QWidget()
        page.setObjectName("DashboardPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(
            HOME["pad_x"],
            HOME["pad_top"],
            HOME["pad_x"],
            HOME["pad_bottom"],
        )
        outer.setSpacing(0)

        self._column = QWidget(page)
        self._column.setObjectName("DashboardColumn")
        self._column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col = QVBoxLayout(self._column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        column = self._column

        period = greeting_for_now()
        greet_key = {
            "morning": "GreetingMorning",
            "afternoon": "GreetingAfternoon",
            "evening": "GreetingEvening",
        }[period]
        greet = TitleLabel(hd[greet_key].format(self._info.username), column)
        greet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(greet)

        sub_row = QHBoxLayout()
        sub_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_row.setSpacing(HOME["sub_gap"])
        sub_a = SubtitleLabel(hd["SubtitleLead"], column)
        sub_b = SubtitleLabel(hd["SubtitleAccent"], column)
        try:
            sub_b.setTextColor(PRIMARY, PRIMARY)
        except Exception:
            sub_b.setStyleSheet(f"color: {PRIMARY};")
        sub_row.addWidget(sub_a)
        sub_row.addWidget(sub_b)
        col.addSpacing(HOME["after_greet"])
        col.addLayout(sub_row)

        col.addSpacing(HOME["section_gap"])
        col.addWidget(SubtitleLabel(hd["PcInfoSection"], column))
        col.addSpacing(HOME["section_title_gap"])

        chips_host = QWidget(column)
        chips_row = QHBoxLayout(chips_host)
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(HOME["gap"])
        for icon, title, value in (
            (FluentIcon.INFO, hd["ChipOs"], self._info.os_name),
            (FluentIcon.DEVELOPER_TOOLS, hd["ChipCpu"], self._info.cpu),
            (FluentIcon.LIBRARY, hd["ChipRam"], self._info.ram),
            (FluentIcon.PHOTO, hd["ChipGpu"], self._info.gpu),
            (FluentIcon.SPEED_HIGH, hd["ChipAccel"], self._info.accelerator),
        ):
            card = InfoSettingCard(icon, title, value, chips_host)
            chips_row.addWidget(card, 1)
        col.addWidget(chips_host)

        col.addSpacing(HOME["prompt_gap"])
        self.prompt = _PromptBox(column)
        self.prompt.submitted.connect(self._on_prompt)
        self.prompt.attach_clicked.connect(self.open_files.emit)
        self.prompt.stop_clicked.connect(self._stop_generate)
        col.addWidget(self.prompt)

        self.status_label = BodyLabel("", column)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        col.addSpacing(HOME["hint_gap"])
        col.addWidget(self.status_label)

        self.preview_label = QLabel(column)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(0)
        self.preview_label.hide()
        col.addSpacing(HOME["gap"])
        col.addWidget(self.preview_label)

        self.open_result_btn = make_button(
            hd.get("OpenResult", "Open"), "secondary", column, FluentIcon.FOLDER
        )
        self.open_result_btn.clicked.connect(self._open_last_result)
        self.open_result_btn.hide()
        open_row = QHBoxLayout()
        open_row.addStretch(1)
        open_row.addWidget(self.open_result_btn)
        open_row.addStretch(1)
        col.addLayout(open_row)

        hint = BodyLabel(hd["PromptHint"], column)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        col.addSpacing(HOME["hint_gap"])
        col.addWidget(hint)

        outer.addStretch(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(_SIDE_STRETCH)
        row.addWidget(column, _COLUMN_STRETCH)
        row.addStretch(_SIDE_STRETCH)
        outer.addLayout(row)
        outer.addStretch(2)

        scroll.setWidget(page)
        self._scroll = scroll
        self._page = page
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        self.apply_theme_bg()

    def apply_theme_bg(self):
        """Scroll + inner page default to white - paint both with ``PAGE['bg']``."""
        apply_page_bg(self, self._scroll, self._page)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_generate_gate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        apply_content_column_width(
            self._column,
            self._scroll.viewport().width() - HOME["pad_x"] * 2,
        )

    def set_external_gpu_busy(self, busy: bool):
        """Another tool owns the shared infer worker — block Generate."""
        self._external_gpu_busy = bool(busy)
        self.refresh_generate_gate()

    def refresh_generate_gate(self):
        """CUDA + model On gate for the Generate button."""
        hd = tr["HomeDashboard"]
        ok, reason = cuda_ready_for_generate()
        self._cuda_ok = ok
        self._cuda_reason = reason
        modes = selectable_modes()
        if self._active_run_id is not None:
            return
        if self._external_gpu_busy:
            tip = hd.get(
                "GenerateGpuBusy",
                "Another tool is using the GPU. Wait for it to finish or stop it first.",
            )
            self.prompt.set_generate_enabled(False, tip)
            if not self._last_result_path:
                self.status_label.setText(tip)
            return
        if not ok:
            self.prompt.set_generate_enabled(False, reason or hd["GenerateBlockedCuda"])
            self.status_label.setText(reason or hd["GenerateBlockedCuda"])
            return
        if not modes:
            tip = hd["GenerateNoModel"]
            self.prompt.set_generate_enabled(False, tip)
            if not self._last_result_path:
                self.status_label.setText(tip)
            return
        self.prompt.set_generate_enabled(True, "")
        if not self._last_result_path:
            self.status_label.setText("")

    def _on_prompt(self, text: str):
        """Route tool shortcuts; otherwise Generate with FLUX.2."""
        q = text.lower().strip()
        if any(k in q for k in ("setting", "config", "theme", "model")):
            self.open_settings.emit()
            return
        if any(k in q for k in ("subtitle", "watermark", "video", "inpaint", "sttn", "lama")):
            self.open_video.emit()
            return
        if any(k in q for k in ("upscale", "enhance", "esrgan", "real-esrgan")):
            self.open_upscale.emit()
            return
        if any(k in q for k in ("low light", "lowlight", "mirnet")):
            self.open_low_light.emit()
            return
        if any(k in q for k in ("background", "bg", "cutout", "remove bg", "rembg")):
            self.open_bg_remove.emit()
            return
        if any(k in q for k in ("open file", "upload", "attach")):
            self.open_files.emit()
            return
        self._start_generate(text)

    def _start_generate(self, prompt: str):
        hd = tr["HomeDashboard"]
        gen = tr["Generate"]
        prompt = (prompt or "").strip()
        if not prompt:
            InfoBar.warning(
                title=hd.get("Generate", "Generate"),
                content=hd["GenerateEmpty"],
                duration=config.infoBarDurationMs,
                parent=self,
            )
            return

        from ui.gpu_busy import gpu_busy_message, is_gpu_busy

        if self._external_gpu_busy or is_gpu_busy():
            InfoBar.warning(
                title=gen.get("Title", "Generate"),
                content=gpu_busy_message(),
                duration=config.infoBarDurationMs,
                parent=self,
            )
            return

        self.refresh_generate_gate()
        if not self._cuda_ok:
            InfoBar.error(
                title=gen.get("Title", "Generate"),
                content=self._cuda_reason or hd["GenerateBlockedCuda"],
                duration=config.infoBarDurationMs,
                parent=self,
            )
            return

        modes = selectable_modes()
        if not modes:
            InfoBar.warning(
                title=gen.get("Title", "Generate"),
                content=hd["GenerateNoModel"],
                duration=config.infoBarDurationMs,
                parent=self,
            )
            return

        mode = ensure_selected_mode_valid()
        if mode not in modes:
            mode = modes[0]
            config.set(config.generateMode, mode)

        if self._active_run_id is not None:
            return

        out_dir_raw = str(config.saveDirectory.value or "").strip()
        if out_dir_raw:
            out_dir = Path(out_dir_raw).expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)
            fd, output_path = tempfile.mkstemp(
                prefix="midgard_flux_", suffix=".png", dir=str(out_dir)
            )
            os.close(fd)
        else:
            fd, output_path = tempfile.mkstemp(prefix="midgard_flux_", suffix=".png")
            os.close(fd)

        try:
            width = int(config.generateWidth.value)
            height = int(config.generateHeight.value)
            steps = int(config.generateSteps.value)
        except (TypeError, ValueError):
            width, height, steps = 1024, 1024, 4

        payload = {
            "prompt": prompt,
            "output_path": output_path,
            "mode": mode.value if isinstance(mode, GenerateMode) else str(mode),
            "width": width,
            "height": height,
            "steps": steps,
            "guidance": 1.0,
            "hardware_acceleration": bool(config.hardwareAcceleration.value),
        }

        self.prompt.set_generating(True)
        self.processing_changed.emit(True)
        self.status_label.setText(hd["Generating"].format(0))
        self.open_result_btn.hide()

        client = InferClient.instance()
        run_id = client.start_job(
            JobType.GENERATE,
            payload,
            on_progress=lambda p: self._progress_signal.emit(int(p)),
            on_error=lambda msg: self._error_signal.emit(str(msg or "")),
            on_result=lambda path: self._result_signal.emit(str(path or "")),
            on_done=lambda: self._done_signal.emit(),
            coalesce=False,
        )
        if run_id < 0:
            self._finish_generate()
            InfoBar.warning(
                title=gen.get("Title", "Generate"),
                content=gpu_busy_message(),
                duration=config.infoBarDurationMs,
                parent=self,
            )
            self.refresh_generate_gate()
            return
        self._active_run_id = run_id

    def _on_progress_ui(self, p: int):
        hd = tr["HomeDashboard"]
        self.status_label.setText(hd["Generating"].format(max(0, min(100, int(p)))))

    def _on_error_ui(self, msg: str):
        gen = tr["Generate"]
        self._finish_generate()
        if msg == "__cancelled__":
            self.status_label.setText("")
            self.refresh_generate_gate()
            return
        text = str(msg or "")
        lower = text.lower()
        if text == "BUSY" or lower == "busy":
            from ui.gpu_busy import gpu_busy_message

            content = gpu_busy_message()
        elif "memory" in lower or "oom" in lower:
            content = gen["ErrorOutOfMemory"]
        elif "download" in lower or "huggingface" in lower:
            content = gen["ErrorDownload"]
        else:
            content = text or gen["ErrorCuda"]
        InfoBar.error(
            title=gen.get("Title", "Generate"),
            content=content,
            duration=config.infoBarDurationMs,
            parent=self,
        )
        self.status_label.setText(content)
        self.refresh_generate_gate()

    def _on_result_ui(self, path: str):
        hd = tr["HomeDashboard"]
        gen = tr["Generate"]
        self._last_result_path = path
        self._finish_generate()
        self.status_label.setText(hd["GenerateReady"].format(path))
        self._show_preview(path)
        self.open_result_btn.show()
        InfoBar.success(
            title=gen.get("Title", "Generate"),
            content=hd["GenerateReady"].format(Path(path).name),
            duration=config.infoBarDurationMs,
            parent=self,
        )
        self.prompt.input.clear()
        self.refresh_generate_gate()

    def _on_done_ui(self):
        if self._active_run_id is not None:
            QTimer.singleShot(0, self._maybe_clear_busy)

    def _maybe_clear_busy(self):
        if self._active_run_id is not None:
            self._finish_generate()
            self.refresh_generate_gate()

    def _finish_generate(self):
        self._active_run_id = None
        self.prompt.set_generating(False)
        self.processing_changed.emit(False)

    def _stop_generate(self):
        rid = self._active_run_id
        if rid is None:
            return
        try:
            InferClient.instance().cancel(rid)
        except Exception:
            pass

    def _show_preview(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            self.preview_label.hide()
            return
        scaled = pix.scaled(
            _PREVIEW_MAX,
            _PREVIEW_MAX,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.show()

    def _open_last_result(self):
        if not self._last_result_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_result_path))
