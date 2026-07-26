"""Fullscreen retouch dialog after Remove BG — brush + selection + LAMA."""

from __future__ import annotations

import os
import traceback

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
    QSizePolicy,
)
from qfluentwidgets import (
    BodyLabel, SubtitleLabel, FluentIcon, ProgressBar,
)

from backend.config import BASE_DIR, config, tr
from backend.tools import diag
from ui.component.controls.button_styles import make_button, make_toggle_button, paint_toggle_button
from ui.component.controls.slider_styles import PrimarySlider
from ui.component.workspace.editor_page import EditorPage
from ui.component.preview.retouch_canvas import RetouchCanvas, RetouchTool
from ui.theme import DIALOG, FORM, PRIMARY, SECTION, TEXT, TEXT_SECONDARY, BG


def _lama_model_path() -> str:
    return os.path.join(BASE_DIR, "models", "big-lama", "big-lama.pt")


# Primary tool kinds in the Tools section
_KIND_BRUSH = "brush"
_KIND_LASSO = "lasso"
_KIND_PEN = "pen"
_KIND_RECT = "rect"


class BgRetouchDialog(QDialog):
    """
    Full-window retouch after background removal.

    Flow:
      1. Choose Brush / Lasso / Pen / Rectangle
      2. For selection tools: draw a closed region, then Remove or Fill (LAMA)
      3. Brush paints freely (Eraser / Restore / Mask) with size + hardness
      Space+drag pans · Ctrl+wheel zooms · Ctrl+Z undo
    """

    finished_image = Signal(object)  # PIL RGBA
    _lama_done = Signal(object, object)  # rgb ndarray or None, error str|None
    _status = Signal(str)
    _progress = Signal(int)  # 0–100

    def __init__(self, rgba: Image.Image, parent=None, original: Image.Image | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr["BgRetouch"]["Title"])
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setModal(True)
        self.resize(config.retouchWindowW, config.retouchWindowH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Scope to QDialog so bare props don't cascade onto SectionCard children.
        self.setStyleSheet(
            f"QDialog {{ background-color: {BG}; color: {TEXT}; border: none; }}"
        )
        self._busy = False
        self._close_after_cancel = False
        self._progress_value = 0
        self._pending_lama_mask: np.ndarray | None = None
        self._tool_kind = _KIND_BRUSH
        self._brush_mode = RetouchTool.ERASE_ALPHA
        self._mask_paint_mode = RetouchTool.MASK  # MASK or ERASE_MASK

        self.canvas = RetouchCanvas(self)
        # Defer set_image until after show — window appears instantly
        self._pending_rgba = rgba
        self._pending_original = original

        # Same shell as tool pages: preview SectionCard + right rail (shared width)
        self.editor = EditorPage(
            self.canvas,
            self,
            preview_title=tr["BgRetouch"].get("Canvas", tr["BgRetouch"]["Title"]),
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.editor)

        rail = self.editor.right_rail
        gap = DIALOG["tool_gap"]

        def _grid_buttons(parent: QWidget, items, columns: int):
            """items: list of (key, label) → (dict key→btn, wrap widget)."""
            wrap = QWidget(parent)
            grid = QGridLayout(wrap)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(gap)
            for c in range(columns):
                grid.setColumnStretch(c, 1)
            buttons = {}
            for i, (key, label) in enumerate(items):
                btn = make_toggle_button(label, wrap)
                btn.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                buttons[key] = btn
                grid.addWidget(btn, i // columns, i % columns)
            return buttons, wrap

        # --- Tools ---
        tools_body = QWidget(rail)
        tools_layout = QVBoxLayout(tools_body)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(SECTION["spacing"])
        self._kind_group = QButtonGroup(self)
        self._kind_buttons, kind_wrap = _grid_buttons(
            tools_body,
            [
                (_KIND_BRUSH, tr["BgRetouch"]["ToolBrush"]),
                (_KIND_LASSO, tr["BgRetouch"]["ToolLasso"]),
                (_KIND_PEN, tr["BgRetouch"]["ToolPen"]),
                (_KIND_RECT, tr["BgRetouch"]["ToolRect"]),
            ],
            2,
        )
        tools_layout.addWidget(kind_wrap)
        for kind, btn in self._kind_buttons.items():
            self._kind_group.addButton(btn)
            btn.clicked.connect(lambda checked=False, k=kind: self._select_kind(k))
        self.editor.add_section(tr["BgRetouch"]["Tools"], tools_body)

        # --- Brush (modes + size / hardness + mask actions) ---
        brush_body = QWidget(rail)
        brush_layout = QVBoxLayout(brush_body)
        brush_layout.setContentsMargins(0, 0, 0, 0)
        brush_layout.setSpacing(SECTION["spacing"])

        self.brush_mode_label = SubtitleLabel(tr["BgRetouch"]["BrushMode"], brush_body)
        brush_layout.addWidget(self.brush_mode_label)

        self._mode_group = QButtonGroup(self)
        self._mode_buttons, mode_wrap = _grid_buttons(
            brush_body,
            [
                (RetouchTool.ERASE_ALPHA, tr["BgRetouch"]["ToolEraser"]),
                (RetouchTool.RESTORE_ALPHA, tr["BgRetouch"]["ToolRestore"]),
                (RetouchTool.MASK, tr["BgRetouch"]["ToolMask"]),
            ],
            3,
        )
        brush_layout.addWidget(mode_wrap)
        self._brush_mode_widgets = [self.brush_mode_label, mode_wrap]
        for mode, btn in self._mode_buttons.items():
            self._mode_group.addButton(btn)
            btn.clicked.connect(
                lambda checked=False, m=mode: self._select_brush_mode(m)
            )

        self.mask_actions_label = SubtitleLabel(tr["BgRetouch"]["MaskActions"], brush_body)
        brush_layout.addWidget(self.mask_actions_label)

        self._mask_paint_group = QButtonGroup(self)
        self._mask_paint_buttons, mask_paint_wrap = _grid_buttons(
            brush_body,
            [
                (RetouchTool.MASK, tr["BgRetouch"]["ToolMaskPaint"]),
                (RetouchTool.ERASE_MASK, tr["BgRetouch"]["ToolEraseMask"]),
            ],
            2,
        )
        brush_layout.addWidget(mask_paint_wrap)
        for mode, btn in self._mask_paint_buttons.items():
            self._mask_paint_group.addButton(btn)
            btn.clicked.connect(
                lambda checked=False, m=mode: self._select_mask_paint_mode(m)
            )

        mask_act_row = QHBoxLayout()
        mask_act_row.setSpacing(gap)
        self.btn_mask_delete = make_button(
            tr["BgRetouch"]["ActionRemove"], "secondary", brush_body
        )
        self.btn_mask_delete.setToolTip(tr["BgRetouch"]["MaskDeleteTip"])
        self.btn_mask_delete.clicked.connect(self._on_delete_mask)
        mask_act_row.addWidget(self.btn_mask_delete)
        self.btn_mask_clear = make_button(
            tr["BgRetouch"]["ClearMask"], "secondary", brush_body
        )
        self.btn_mask_clear.clicked.connect(self._on_clear_mask)
        mask_act_row.addWidget(self.btn_mask_clear)
        mask_act_wrap = QWidget(brush_body)
        mask_act_wrap.setLayout(mask_act_row)
        brush_layout.addWidget(mask_act_wrap)

        self._mask_action_widgets = [
            self.mask_actions_label,
            mask_paint_wrap,
            mask_act_wrap,
        ]

        size_wrap = QWidget(brush_body)
        size_col = QVBoxLayout(size_wrap)
        size_col.setContentsMargins(0, 0, 0, 0)
        size_col.setSpacing(FORM["tight_spacing"])
        size_header = QHBoxLayout()
        size_header.addWidget(SubtitleLabel(tr["BgRetouch"]["BrushSize"], size_wrap))
        self.radius_label = BodyLabel("20 px", size_wrap)
        self.radius_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        size_header.addWidget(self.radius_label, 1)
        size_col.addLayout(size_header)
        self.radius_slider = PrimarySlider(Qt.Horizontal, size_wrap)
        self.radius_slider.setRange(3, 120)
        self.radius_slider.setValue(20)
        self.radius_slider.valueChanged.connect(self._on_radius)
        size_col.addWidget(self.radius_slider)
        brush_layout.addWidget(size_wrap)

        hard_wrap = QWidget(brush_body)
        hard_col = QVBoxLayout(hard_wrap)
        hard_col.setContentsMargins(0, 0, 0, 0)
        hard_col.setSpacing(FORM["tight_spacing"])
        hard_header = QHBoxLayout()
        hard_header.addWidget(SubtitleLabel(tr["BgRetouch"]["BrushHardness"], hard_wrap))
        self.hardness_label = BodyLabel("60%", hard_wrap)
        self.hardness_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hard_header.addWidget(self.hardness_label, 1)
        hard_col.addLayout(hard_header)
        self.hardness_slider = PrimarySlider(Qt.Horizontal, hard_wrap)
        self.hardness_slider.setRange(0, 100)
        self.hardness_slider.setValue(60)
        self.hardness_slider.valueChanged.connect(self._on_hardness)
        hard_col.addWidget(self.hardness_slider)
        brush_layout.addWidget(hard_wrap)
        self.canvas.set_hardness(60)
        self.hardness_label.setText("60%")

        self.editor.add_section(tr["BgRetouch"].get("Brush", "Brush"), brush_body)

        # --- Selection ---
        sel_body = QWidget(rail)
        sel_layout = QVBoxLayout(sel_body)
        sel_layout.setContentsMargins(0, 0, 0, 0)
        sel_layout.setSpacing(SECTION["spacing"])
        sel_row = QHBoxLayout()
        sel_row.setSpacing(gap)
        self.btn_remove = make_button(
            tr["BgRetouch"]["ActionRemove"], "secondary", sel_body
        )
        self.btn_remove.clicked.connect(self._on_remove_selection)
        sel_row.addWidget(self.btn_remove)
        self.btn_clear_sel = make_button(
            tr["BgRetouch"]["ActionClearSelection"], "secondary", sel_body
        )
        self.btn_clear_sel.clicked.connect(self.canvas.clear_selection)
        sel_row.addWidget(self.btn_clear_sel)
        sel_layout.addLayout(sel_row)

        self.btn_fill = make_button(
            tr["BgRetouch"]["ActionFill"], "primary", sel_body, FluentIcon.EDIT
        )
        self.btn_fill.clicked.connect(self._apply_lama)
        sel_layout.addWidget(self.btn_fill)

        undo_row = QHBoxLayout()
        undo_row.setSpacing(gap)
        self.btn_undo = make_button(tr["BgRetouch"]["Undo"], "secondary", sel_body)
        self.btn_undo.clicked.connect(self.canvas.undo)
        undo_row.addWidget(self.btn_undo)
        self.btn_redo = make_button(tr["BgRetouch"]["Redo"], "secondary", sel_body)
        self.btn_redo.clicked.connect(self.canvas.redo)
        undo_row.addWidget(self.btn_redo)
        sel_layout.addLayout(undo_row)
        self.editor.add_section(tr["BgRetouch"]["Selection"], sel_body)

        # --- Status / progress / Done-Cancel (footer, ActionBar-like) ---
        footer = QWidget(rail)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(SECTION["spacing"])

        self.progress_panel = QWidget(footer)
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(0, 4, 0, 0)
        progress_layout.setSpacing(FORM["tight_spacing"])
        self.progress_label = BodyLabel(
            tr["BgRetouch"]["LamaProcessing"].format(0), self.progress_panel
        )
        self.progress_label.setStyleSheet(f"color:{PRIMARY}; font-weight:500;")
        progress_layout.addWidget(self.progress_label)
        self.progress_bar = ProgressBar(self.progress_panel)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        self.progress_panel.setVisible(False)
        footer_layout.addWidget(self.progress_panel)

        self.status = BodyLabel("", footer)
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{TEXT_SECONDARY};")
        footer_layout.addWidget(self.status)

        self.btn_done = make_button(tr["BgRetouch"]["Done"], "primary", footer)
        self.btn_done.clicked.connect(self._on_done)
        footer_layout.addWidget(self.btn_done)

        self.btn_cancel = make_button(tr["BgRetouch"]["Cancel"], "secondary", footer)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        footer_layout.addWidget(self.btn_cancel)

        self.editor.add_rail_stretch(1)
        self.editor.add_section(
            tr["BgRetouch"].get("Actions", tr["SubtitleExtractorGUI"].get("Setting", "Actions")),
            footer,
        )

        self._lama_done.connect(self._on_lama_done)
        self._status.connect(self.status.setText)
        self._progress.connect(self._on_progress)
        self.canvas.history_changed.connect(self._refresh_history_buttons)
        self.canvas.selection_changed.connect(self._refresh_selection_buttons)
        self.canvas.image_changed.connect(self._refresh_mask_buttons)

        # Default: Brush + Eraser
        self._kind_buttons[_KIND_BRUSH].setChecked(True)
        self._mode_buttons[RetouchTool.ERASE_ALPHA].setChecked(True)
        self._mask_paint_buttons[RetouchTool.MASK].setChecked(True)
        self._select_kind(_KIND_BRUSH)
        self._refresh_history_buttons()
        self._refresh_selection_buttons()
        self._refresh_mask_buttons()

        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(180)
        self._progress_timer.timeout.connect(self._tick_progress)

        self._image_size = rgba.size
        # Caller presents the window (present_editor_dialog) — do not show here

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_rgba is not None:
            QTimer.singleShot(0, self._load_pending_image)

    def _load_pending_image(self):
        rgba = self._pending_rgba
        original = self._pending_original
        self._pending_rgba = None
        self._pending_original = None
        if rgba is None:
            return
        import time

        t0 = time.perf_counter()
        self.canvas.set_image(rgba, original=original)
        iw, ih = rgba.size
        if max(iw, ih) < 900:
            self.canvas.zoom_actual()
        ms = (time.perf_counter() - t0) * 1000.0
        diag.event(f"Retouch canvas ready  {iw}x{ih}  {ms:.0f}ms")

    def _set_brush_mode_visible(self, visible: bool):
        for w in self._brush_mode_widgets:
            w.setVisible(visible)

    def _set_mask_actions_visible(self, visible: bool):
        for w in self._mask_action_widgets:
            w.setVisible(visible)

    def _select_kind(self, kind: str):
        self._tool_kind = kind
        for k, btn in self._kind_buttons.items():
            btn.setChecked(k == kind)
            paint_toggle_button(btn)
        is_brush = kind == _KIND_BRUSH
        self._set_brush_mode_visible(is_brush)
        self._set_mask_actions_visible(
            is_brush and self._brush_mode == RetouchTool.MASK
        )

        if kind == _KIND_BRUSH:
            self._apply_brush_tool()
        elif kind == _KIND_LASSO:
            self.canvas.set_tool(RetouchTool.LASSO)
        elif kind == _KIND_PEN:
            self.canvas.set_tool(RetouchTool.PEN)
        elif kind == _KIND_RECT:
            self.canvas.set_tool(RetouchTool.RECT)

    def _select_brush_mode(self, mode: RetouchTool):
        self._brush_mode = mode
        for m, btn in self._mode_buttons.items():
            btn.setChecked(m == mode)
            paint_toggle_button(btn)
        show_mask = (
            self._tool_kind == _KIND_BRUSH and mode == RetouchTool.MASK
        )
        self._set_mask_actions_visible(show_mask)
        if self._tool_kind == _KIND_BRUSH:
            self._apply_brush_tool()

    def _select_mask_paint_mode(self, mode: RetouchTool):
        self._mask_paint_mode = mode
        for m, btn in self._mask_paint_buttons.items():
            btn.setChecked(m == mode)
            paint_toggle_button(btn)
        if self._tool_kind == _KIND_BRUSH and self._brush_mode == RetouchTool.MASK:
            self.canvas.set_tool(mode)

    def _apply_brush_tool(self):
        if self._brush_mode == RetouchTool.MASK:
            self.canvas.set_tool(self._mask_paint_mode)
        else:
            self.canvas.set_tool(self._brush_mode)

    def _refresh_history_buttons(self):
        self.btn_undo.setEnabled(self.canvas.can_undo() and not self._busy)
        self.btn_redo.setEnabled(self.canvas.can_redo() and not self._busy)

    def _refresh_selection_buttons(self):
        has = self.canvas.has_selection() and not self._busy
        self.btn_remove.setEnabled(has)
        self.btn_clear_sel.setEnabled(has)
        # Fill stays enabled when not busy (selection or painted mask)

    def _refresh_mask_buttons(self):
        has_mask = self.canvas.has_painted_mask() and not self._busy
        self.btn_mask_delete.setEnabled(has_mask)
        self.btn_mask_clear.setEnabled(has_mask)

    def _on_remove_selection(self):
        if not self.canvas.has_selection():
            self.status.setText(tr["BgRetouch"]["NoSelection"])
            return
        diag.run("Retouch remove selection")
        self.canvas.remove_selection()
        self.status.setText(tr["BgRetouch"]["RemovedSelection"])

    def _on_delete_mask(self):
        if not self.canvas.has_painted_mask():
            self.status.setText(tr["BgRetouch"]["NoMask"])
            return
        diag.run("Retouch erase masked pixels")
        self.canvas.remove_painted_mask()
        self.status.setText(tr["BgRetouch"]["RemovedMask"])
        self._refresh_mask_buttons()

    def _on_clear_mask(self):
        diag.run("Retouch clear mask")
        self.canvas.clear_mask()
        self.status.setText(tr["BgRetouch"]["ClearedMask"])
        self._refresh_mask_buttons()

    def _on_radius(self, value: int):
        self.canvas.set_radius(value)
        self.radius_label.setText(f"{value} px")

    def _on_hardness(self, value: int):
        self.canvas.set_hardness(value)
        self.hardness_label.setText(f"{value}%")

    @Slot(int)
    def _on_progress(self, value: int):
        value = max(0, min(100, int(value)))
        if value >= 45 and value < 95 and self._busy and not self._progress_timer.isActive():
            self._progress_timer.start()
        if value >= 95:
            self._progress_timer.stop()
        self._progress_value = value
        self.progress_bar.setValue(value)
        self.progress_label.setText(tr["BgRetouch"]["LamaProcessing"].format(value))
        self.progress_panel.setVisible(True)

    def _tick_progress(self):
        """Creep toward 90% while inference is blocked in the worker."""
        if not self._busy:
            self._progress_timer.stop()
            return
        if self._progress_value < 90:
            step = 1 if self._progress_value < 70 else (1 if self._progress_value % 2 == 0 else 0)
            if step:
                self._on_progress(self._progress_value + step)

    def _set_busy(self, busy: bool):
        """Lock tools/canvas while Fill runs — only Stop is available until done."""
        self._busy = busy
        self.canvas.set_interaction_enabled(not busy)

        editable = not busy
        self.btn_fill.setEnabled(editable)
        self.btn_done.setEnabled(editable)
        self.btn_remove.setEnabled(editable and self.canvas.has_selection())
        self.btn_clear_sel.setEnabled(editable and self.canvas.has_selection())
        self.btn_mask_delete.setEnabled(editable and self.canvas.has_painted_mask())
        self.btn_mask_clear.setEnabled(editable and self.canvas.has_painted_mask())
        self.radius_slider.setEnabled(editable)
        self.hardness_slider.setEnabled(editable)
        for btn in self._kind_buttons.values():
            btn.setEnabled(editable)
        for btn in self._mode_buttons.values():
            btn.setEnabled(editable)
        for btn in self._mask_paint_buttons.values():
            btn.setEnabled(editable)
        self._refresh_history_buttons()
        if not busy:
            self._refresh_selection_buttons()
            self._refresh_mask_buttons()

        # Cancel closes dialog when idle; Stop cancels Fill when busy
        if busy:
            self.btn_cancel.setText(tr["BgRetouch"].get("StopFill", "Stop"))
            self.progress_panel.setVisible(True)
            self._on_progress(0)
        else:
            self.btn_cancel.setText(tr["BgRetouch"]["Cancel"])
            self._progress_timer.stop()

    def _on_cancel_clicked(self):
        if self._busy:
            self._cancel_lama()
            return
        self.reject()

    def _cancel_lama(self):
        if not self._busy:
            return
        diag.run("LAMA fill CANCEL requested")
        self.status.setText(tr["BgRetouch"].get("LamaCancelled", "Fill cancelled."))
        try:
            from backend.tools.infer_client import InferClient

            InferClient.instance().cancel()
        except Exception:
            traceback.print_exc()
            # Force unlock if cancel plumbing fails
            self._pending_lama_mask = None
            self._set_busy(False)
            self.progress_panel.setVisible(False)

    def reject(self):
        if self._busy:
            # Closing while Fill runs → cancel job first, then close after unlock
            self._close_after_cancel = True
            self._cancel_lama()
            return
        diag.event("Retouch dialog CANCEL")
        super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            self._close_after_cancel = True
            self._cancel_lama()
            return
        super().closeEvent(event)

    def _apply_lama(self):
        if self._busy:
            return
        img = self.canvas.get_image()
        sel = self.canvas.selection_as_mask()
        painted = self.canvas.get_mask()

        if sel is not None and np.any(sel):
            mask = sel
        elif painted is not None and painted.any():
            mask = painted
        else:
            self.status.setText(tr["BgRetouch"]["NoSelection"])
            return

        path = _lama_model_path()
        if not os.path.isfile(path):
            self.status.setText(tr["BgRetouch"]["MissingLama"])
            return

        from backend.tools.infer_client import InferClient
        from backend.tools.infer_protocol import JobType

        self._pending_lama_mask = mask.copy()
        self._set_busy(True)
        self.status.setText(tr["BgRetouch"]["LamaRunning"])
        self._progress.emit(5)
        src = "selection" if sel is not None and np.any(sel) else "painted_mask"
        diag.run(f"LAMA fill START  mask={src}  model={os.path.basename(path)}")
        diag.model(f"LAMA  {_lama_model_path()}")
        diag.progress("lama_retouch", 0, "LAMA fill", force=True)

        client = InferClient.instance()
        img_path = client.make_temp_path("lama_img_", ".png")
        mask_path = client.make_temp_path("lama_mask_", ".png")
        out_path = client.make_temp_path("lama_out_", ".png")
        img.convert("RGBA").save(img_path, format="PNG")
        Image.fromarray(mask.copy(), mode="L").save(mask_path, format="PNG")
        self._lama_temps = (img_path, mask_path, out_path)

        def on_progress(p: int):
            diag.progress("lama_retouch", p, "LAMA fill")
            self._progress.emit(p)

        def on_log(msg: str):
            diag.worker(f"LAMA  {msg}")
            lower = msg.lower()
            if "load" in lower:
                self._status.emit(tr["BgRetouch"]["LamaLoading"])
            elif "inpaint" in lower:
                self._status.emit(tr["BgRetouch"]["LamaInpainting"])
            else:
                self._status.emit(tr["BgRetouch"]["LamaPreparing"])

        def on_result(result_path: str):
            rgb_out = None
            err = None
            try:
                rgba = Image.open(result_path).convert("RGBA")
                rgb_out = np.asarray(rgba.convert("RGB"))
            except Exception as e:
                traceback.print_exc()
                err = str(e)
            finally:
                for p in self._lama_temps:
                    InferClient.unlink_quiet(p)
                self._lama_temps = ()
            self._lama_done.emit(rgb_out, err)

        def on_error(msg: str):
            for p in getattr(self, "_lama_temps", ()):
                InferClient.unlink_quiet(p)
            self._lama_temps = ()
            if msg in ("__cancelled__", "TIMEOUT", "CRASH", "BUSY"):
                self._lama_done.emit(None, msg if msg != "__cancelled__" else "Cancelled")
            else:
                self._lama_done.emit(None, msg)

        client.start_job(
            JobType.LAMA_RETOUCH,
            {
                "image_path": img_path,
                "mask_path": mask_path,
                "output_path": out_path,
                "model_path": path,
                "hardware_acceleration": bool(config.hardwareAcceleration.value),
            },
            on_progress=on_progress,
            on_log=on_log,
            on_result=on_result,
            on_error=on_error,
            coalesce=False,
        )

    @Slot(object, object)
    def _on_lama_done(self, rgb, err):
        self._progress_timer.stop()
        close_after = bool(getattr(self, "_close_after_cancel", False))
        self._close_after_cancel = False
        if err:
            self._pending_lama_mask = None
            self._set_busy(False)
            self.progress_panel.setVisible(False)
            cancelled = str(err).lower() in ("cancelled", "__cancelled__")
            if cancelled:
                self.status.setText(tr["BgRetouch"].get("LamaCancelled", "Fill cancelled."))
                diag.run("LAMA fill CANCELLED")
            else:
                self.status.setText(tr["BgRetouch"]["LamaFailed"].format(err))
                diag.error(f"LAMA fill FAILED  {err}")
            diag.progress("lama_retouch", 100, "LAMA fill", force=True)
            if close_after:
                diag.event("Retouch dialog CANCEL")
                super().reject()
            return
        self._on_progress(100)
        mask = self._pending_lama_mask
        self._pending_lama_mask = None
        if rgb is not None and mask is not None:
            self.canvas.apply_rgb_patch(rgb, mask)
        self._set_busy(False)
        self._refresh_mask_buttons()
        self.status.setText(tr["BgRetouch"]["LamaDone"])
        diag.run("LAMA fill DONE")
        diag.progress("lama_retouch", 100, "LAMA fill", force=True)
        QTimer.singleShot(config.retouchProgressHideMs, self._hide_progress)
        if close_after:
            diag.event("Retouch dialog CANCEL")
            super().reject()

    def _hide_progress(self):
        if not self._busy:
            self.progress_panel.setVisible(False)
            self.progress_bar.setValue(0)
            self._progress_value = 0

    def _on_done(self):
        if self._busy:
            return
        img = self.canvas.get_image()
        if img is not None:
            diag.event(f"Retouch dialog DONE  {img.size[0]}x{img.size[1]}")
            self.finished_image.emit(img)
        else:
            diag.event("Retouch dialog DONE  (empty)")
        self.accept()
