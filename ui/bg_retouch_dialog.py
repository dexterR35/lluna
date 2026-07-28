"""Fullscreen retouch dialog after Remove BG - brush + selection + LAMA."""

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
    QFileDialog,
    QSizePolicy,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon, LineEdit, ProgressBar,
)

from backend.config import BASE_DIR, config, tr
from backend.tools import diag
from ui.component.controls.button_styles import make_button, make_toggle_button, paint_toggle_button
from ui.component.controls.slider_styles import PrimarySlider
from ui.component.workspace.editor_page import EditorPage
from ui.component.preview.retouch_canvas import RetouchCanvas, RetouchTool
from ui.component.select_object_controller import SelectObjectController
from ui.theme import DIALOG, FORM, PRIMARY, SECTION, TEXT, TEXT_SECONDARY, BG


def _rail_label(text: str, parent: QWidget) -> BodyLabel:
    """Small secondary label — matches Settings rail field headers."""
    lbl = BodyLabel(text, parent)
    lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
    return lbl


def _lama_model_path() -> str:
    return os.path.join(BASE_DIR, "models", "big-lama", "big-lama.pt")


# Primary tool kinds in the Tools section
_KIND_BRUSH = "brush"
_KIND_LASSO = "lasso"
_KIND_PEN = "pen"
_KIND_RECT = "rect"
_KIND_AI = "ai"


class BgRetouchDialog(QDialog):
    """
    Full-window retouch after background removal.

    Flow:
      1. Choose Brush / Lasso / Pen / Rectangle
      2. For selection tools: draw a closed region, then Remove or Fill (LAMA)
      3. Brush paints freely (Eraser / Restore / Mask) with size + hardness
      Space+drag pans · Ctrl+wheel zooms · Ctrl+Z undo

    Select Object (SAM2) is only in Protect areas — not here.
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
        self._select_busy = False

        self.select_controller = SelectObjectController(self)
        self.select_controller.busy_changed.connect(self._on_select_busy)
        self.select_controller.failed.connect(self._on_select_failed)
        self.select_controller.finished.connect(self._on_select_finished)
        self.select_controller.progress.connect(self._progress.emit)

        self.canvas = RetouchCanvas(self)
        self._pending_rgba = rgba
        self._pending_original = original

        self.editor = EditorPage(
            self.canvas,
            self,
            preview_title=None,
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.editor)

        rail = self.editor.right_rail
        gap = DIALOG["tool_gap"]

        def _grid_buttons(parent: QWidget, items, columns: int):
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
                (_KIND_AI, "AI object"),
            ],
            2,
        )
        tools_layout.addWidget(kind_wrap)
        for kind, btn in self._kind_buttons.items():
            self._kind_group.addButton(btn)
            btn.clicked.connect(lambda checked=False, k=kind: self._select_kind(k))

        self.ai_name_edit = LineEdit(tools_body)
        self.ai_name_edit.setPlaceholderText("Object name, or click the object")
        self.ai_name_edit.returnPressed.connect(self._run_select_from_text)
        tools_layout.addWidget(self.ai_name_edit)
        self.btn_ai_run = make_button(
            "Select object", "secondary", tools_body
        )
        self.btn_ai_run.clicked.connect(self._run_select_from_text)
        tools_layout.addWidget(self.btn_ai_run)

        self.editor.add_section(tr["BgRetouch"]["Tools"], tools_body)

        # --- Brush (modes + size / hardness + mask actions) ---
        brush_body = QWidget(rail)
        brush_layout = QVBoxLayout(brush_body)
        brush_layout.setContentsMargins(0, 0, 0, 0)
        brush_layout.setSpacing(SECTION["spacing"])

        self.brush_mode_label = _rail_label(tr["BgRetouch"]["BrushMode"], brush_body)
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

        self.mask_actions_label = _rail_label(tr["BgRetouch"]["MaskActions"], brush_body)
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
        paint_tip = tr["BgRetouch"].get("ToolMaskPaintTip", "")
        erase_tip = tr["BgRetouch"].get("ToolEraseMaskTip", "")
        if paint_tip:
            self._mask_paint_buttons[RetouchTool.MASK].setToolTip(paint_tip)
        if erase_tip:
            self._mask_paint_buttons[RetouchTool.ERASE_MASK].setToolTip(erase_tip)

        mask_act_row = QHBoxLayout()
        mask_act_row.setSpacing(gap)
        self.btn_mask_clear = make_button(
            tr["BgRetouch"]["ClearMask"], "secondary", brush_body
        )
        self.btn_mask_clear.clicked.connect(self._on_clear_mask)
        mask_act_row.addWidget(self.btn_mask_clear)
        self.btn_mask_invert = make_button("Invert", "secondary", brush_body)
        self.btn_mask_invert.clicked.connect(self.canvas.invert_mask)
        mask_act_row.addWidget(self.btn_mask_invert)
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
        size_header.addWidget(_rail_label(tr["BgRetouch"]["BrushSize"], size_wrap))
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
        hard_header.addWidget(_rail_label(tr["BgRetouch"]["BrushHardness"], hard_wrap))
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

        opacity_wrap = QWidget(brush_body)
        opacity_col = QVBoxLayout(opacity_wrap)
        opacity_col.setContentsMargins(0, 0, 0, 0)
        opacity_col.setSpacing(FORM["tight_spacing"])
        opacity_header = QHBoxLayout()
        opacity_header.addWidget(_rail_label("Opacity", opacity_wrap))
        self.opacity_label = BodyLabel("100%", opacity_wrap)
        self.opacity_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        opacity_header.addWidget(self.opacity_label, 1)
        opacity_col.addLayout(opacity_header)
        self.opacity_slider = PrimarySlider(Qt.Horizontal, opacity_wrap)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        opacity_col.addWidget(self.opacity_slider)
        brush_layout.addWidget(opacity_wrap)

        spacing_wrap = QWidget(brush_body)
        spacing_col = QVBoxLayout(spacing_wrap)
        spacing_col.setContentsMargins(0, 0, 0, 0)
        spacing_col.setSpacing(FORM["tight_spacing"])
        spacing_header = QHBoxLayout()
        spacing_header.addWidget(_rail_label("Spacing", spacing_wrap))
        self.spacing_label = BodyLabel("25%", spacing_wrap)
        self.spacing_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        spacing_header.addWidget(self.spacing_label, 1)
        spacing_col.addLayout(spacing_header)
        self.spacing_slider = PrimarySlider(Qt.Horizontal, spacing_wrap)
        self.spacing_slider.setRange(1, 100)
        self.spacing_slider.setValue(25)
        self.spacing_slider.valueChanged.connect(self._on_spacing)
        spacing_col.addWidget(self.spacing_slider)
        brush_layout.addWidget(spacing_wrap)
        self.canvas.set_spacing(25)

        self.editor.add_section(tr["BgRetouch"].get("Brush", "Brush"), brush_body)

        # --- Independent fill/protect mask layers ---
        layers_body = QWidget(rail)
        layers_layout = QVBoxLayout(layers_body)
        layers_layout.setContentsMargins(0, 0, 0, 0)
        layers_layout.setSpacing(SECTION["spacing"])
        self.layer_combo = ComboBox(layers_body)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_selected)
        layers_layout.addWidget(self.layer_combo)

        layer_row = QHBoxLayout()
        layer_row.setSpacing(gap)
        self.btn_layer_add = make_button("+ Fill", "secondary", layers_body)
        self.btn_layer_add.clicked.connect(
            lambda: self.canvas.add_mask_layer(protect=False)
        )
        layer_row.addWidget(self.btn_layer_add)
        self.btn_layer_protect = make_button("+ Protect", "secondary", layers_body)
        self.btn_layer_protect.clicked.connect(
            lambda: self.canvas.add_mask_layer(protect=True)
        )
        layer_row.addWidget(self.btn_layer_protect)
        self.btn_layer_delete = make_button("Delete", "secondary", layers_body)
        self.btn_layer_delete.clicked.connect(self.canvas.remove_active_layer)
        layer_row.addWidget(self.btn_layer_delete)
        layers_layout.addLayout(layer_row)

        role_row = QHBoxLayout()
        role_row.setSpacing(gap)
        self.btn_role_fill = make_toggle_button("Fill layer", layers_body)
        self.btn_role_fill.clicked.connect(
            lambda: self.canvas.set_active_layer_protect(False)
        )
        role_row.addWidget(self.btn_role_fill)
        self.btn_role_protect = make_toggle_button("Protect layer", layers_body)
        self.btn_role_protect.clicked.connect(
            lambda: self.canvas.set_active_layer_protect(True)
        )
        role_row.addWidget(self.btn_role_protect)
        layers_layout.addLayout(role_row)
        self.btn_layer_visible = make_toggle_button("Visible", layers_body)
        self.btn_layer_visible.clicked.connect(
            lambda checked=False: self.canvas.set_active_layer_visible(
                not self.canvas.active_layer_is_visible()
            )
        )
        layers_layout.addWidget(self.btn_layer_visible)
        self.editor.add_section("Mask layers", layers_body)

        # --- Mask refinement ---
        refine_body = QWidget(rail)
        refine_layout = QVBoxLayout(refine_body)
        refine_layout.setContentsMargins(0, 0, 0, 0)
        refine_layout.setSpacing(SECTION["spacing"])
        self.refine_radius = PrimarySlider(Qt.Horizontal, refine_body)
        self.refine_radius.setRange(1, 32)
        self.refine_radius.setValue(4)
        refine_layout.addWidget(_rail_label("Refine radius", refine_body))
        refine_layout.addWidget(self.refine_radius)
        self._refine_buttons, refine_wrap = _grid_buttons(
            refine_body,
            [
                ("feather", "Feather"),
                ("smooth", "Smooth"),
                ("grow", "Expand"),
                ("shrink", "Shrink"),
                ("edge", "Edge-aware"),
            ],
            2,
        )
        for operation, button in self._refine_buttons.items():
            button.setCheckable(False)
            button.clicked.connect(
                lambda checked=False, op=operation: self._refine_mask(op)
            )
        refine_layout.addWidget(refine_wrap)
        self.editor.add_section("Mask refinement", refine_body)

        # --- Mask project persistence ---
        files_body = QWidget(rail)
        files_layout = QGridLayout(files_body)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(gap)
        self.btn_mask_save = make_button("Save project", "secondary", files_body)
        self.btn_mask_save.clicked.connect(self._save_mask_project)
        files_layout.addWidget(self.btn_mask_save, 0, 0)
        self.btn_mask_load = make_button("Load project", "secondary", files_body)
        self.btn_mask_load.clicked.connect(self._load_mask_project)
        files_layout.addWidget(self.btn_mask_load, 0, 1)
        self.btn_mask_export = make_button("Export PNG", "secondary", files_body)
        self.btn_mask_export.clicked.connect(self._export_mask_png)
        files_layout.addWidget(self.btn_mask_export, 1, 0, 1, 2)
        self.editor.add_section("Mask files", files_body)

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

        mask_sel_row = QGridLayout()
        mask_sel_row.setSpacing(gap)
        self.btn_sel_add = make_button("Add to mask", "secondary", sel_body)
        self.btn_sel_add.clicked.connect(
            lambda: self.canvas.apply_selection_to_mask("add")
        )
        mask_sel_row.addWidget(self.btn_sel_add, 0, 0)
        self.btn_sel_subtract = make_button("Subtract", "secondary", sel_body)
        self.btn_sel_subtract.clicked.connect(
            lambda: self.canvas.apply_selection_to_mask("subtract")
        )
        mask_sel_row.addWidget(self.btn_sel_subtract, 0, 1)
        self.btn_sel_protect = make_button("Protect", "secondary", sel_body)
        self.btn_sel_protect.clicked.connect(
            lambda: self.canvas.apply_selection_to_mask("protect")
        )
        mask_sel_row.addWidget(self.btn_sel_protect, 1, 0, 1, 2)
        sel_layout.addLayout(mask_sel_row)

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

        # --- Footer ---
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
        self.editor.add_section(tr["BgRetouch"].get("Actions", "Actions"), footer)

        self._lama_done.connect(self._on_lama_done)
        self._status.connect(self.status.setText)
        self._progress.connect(self._on_progress)
        self.select_controller.status.connect(self.status.setText)
        self.canvas.history_changed.connect(self._refresh_history_buttons)
        self.canvas.selection_changed.connect(self._refresh_selection_buttons)
        self.canvas.image_changed.connect(self._refresh_mask_buttons)
        self.canvas.layers_changed.connect(self._refresh_layer_controls)
        self.canvas.select_object_clicked.connect(self._on_select_click)

        self._kind_buttons[_KIND_BRUSH].setChecked(True)
        self._mode_buttons[RetouchTool.ERASE_ALPHA].setChecked(True)
        self._mask_paint_buttons[RetouchTool.MASK].setChecked(True)
        self._select_kind(_KIND_BRUSH)
        self._refresh_history_buttons()
        self._refresh_selection_buttons()
        self._refresh_mask_buttons()
        self._refresh_layer_controls()

        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(180)
        self._progress_timer.timeout.connect(self._tick_progress)

        self._image_size = rgba.size

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
        elif kind == _KIND_AI:
            self.canvas.set_tool(RetouchTool.SELECT_OBJECT)

    def _select_brush_mode(self, mode: RetouchTool):
        self._brush_mode = mode
        for m, btn in self._mode_buttons.items():
            btn.setChecked(m == mode)
            paint_toggle_button(btn)
        self._set_mask_actions_visible(
            self._tool_kind == _KIND_BRUSH and mode == RetouchTool.MASK
        )
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
        self.btn_sel_add.setEnabled(has)
        self.btn_sel_subtract.setEnabled(has)
        self.btn_sel_protect.setEnabled(has)

    def _refresh_mask_buttons(self):
        has_mask = self.canvas.has_active_mask() and not self._busy
        self.btn_mask_clear.setEnabled(has_mask)

    def _on_remove_selection(self):
        if not self.canvas.has_selection():
            self.status.setText(tr["BgRetouch"]["NoSelection"])
            return
        diag.run("Retouch remove selection")
        self.canvas.remove_selection()
        self.status.setText(tr["BgRetouch"]["RemovedSelection"])

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

    def _on_opacity(self, value: int):
        self.canvas.set_opacity(value)
        self.opacity_label.setText(f"{value}%")

    def _on_spacing(self, value: int):
        self.canvas.set_spacing(value)
        self.spacing_label.setText(f"{value}%")

    def _on_layer_selected(self, index: int):
        if index >= 0 and index != self.canvas.active_layer_index():
            self.canvas.set_active_layer(index)

    def _refresh_layer_controls(self):
        descriptions = self.canvas.layer_descriptions()
        active = self.canvas.active_layer_index()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layer_combo.addItems(descriptions)
        if descriptions:
            self.layer_combo.setCurrentIndex(active)
        self.layer_combo.blockSignals(False)
        protect = self.canvas.active_layer_is_protect()
        self.btn_role_fill.setChecked(not protect)
        self.btn_role_protect.setChecked(protect)
        paint_toggle_button(self.btn_role_fill)
        paint_toggle_button(self.btn_role_protect)
        self.btn_layer_visible.setChecked(self.canvas.active_layer_is_visible())
        paint_toggle_button(self.btn_layer_visible)
        self.btn_layer_delete.setEnabled(bool(descriptions) and not self._busy)

    def _refine_mask(self, operation: str):
        if not self.canvas.has_active_mask():
            self.status.setText("Paint or select a mask before refining it.")
            return
        self.canvas.refine_mask(operation, self.refine_radius.value())
        self.status.setText(f"Mask {operation} applied.")

    def _save_mask_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save mask project",
            "",
            "Midgard mask project (*.npz)",
        )
        if not path:
            return
        if not path.lower().endswith(".npz"):
            path += ".npz"
        try:
            self.canvas.save_mask_layers(path)
            self.status.setText(f"Mask project saved: {os.path.basename(path)}")
        except Exception as exc:
            self.status.setText(f"Could not save mask project: {exc}")

    def _load_mask_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load mask",
            "",
            "Masks (*.npz *.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".npz"):
                self.canvas.load_mask_layers(path)
            else:
                self.canvas.set_mask(np.asarray(Image.open(path).convert("L")))
            self.status.setText(f"Mask loaded: {os.path.basename(path)}")
        except Exception as exc:
            self.status.setText(f"Could not load mask: {exc}")

    def _export_mask_png(self):
        mask = self.canvas.get_mask()
        if mask is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export composite mask",
            "",
            "PNG mask (*.png)",
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            Image.fromarray(mask, mode="L").save(path, format="PNG")
            self.status.setText(f"Mask exported: {os.path.basename(path)}")
        except Exception as exc:
            self.status.setText(f"Could not export mask: {exc}")

    def _on_select_busy(self, busy: bool):
        self._select_busy = bool(busy)
        self._set_busy(bool(busy))
        if not busy:
            self.progress_panel.setVisible(False)

    def _on_select_failed(self, message: str):
        self.status.setText(message)

    def _on_select_finished(self, mask):
        if mask is None:
            return
        self.canvas.union_object_mask(mask)
        self.status.setText("AI object mask added to the active layer.")

    def _on_select_click(self, x: int, y: int):
        if self._busy or self.canvas.tool != RetouchTool.SELECT_OBJECT:
            return
        image = self.canvas.get_image()
        if image is not None:
            self.select_controller.run(
                image,
                click_xy=(x, y),
                text=self.ai_name_edit.text().strip(),
            )

    def _run_select_from_text(self):
        if self._busy:
            return
        text = self.ai_name_edit.text().strip()
        if not text:
            self.status.setText("Enter an object name or click an object in the image.")
            return
        image = self.canvas.get_image()
        if image is None:
            return
        self._select_kind(_KIND_AI)
        self.select_controller.run(image, text=text)

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
        if not self._busy:
            self._progress_timer.stop()
            return
        if self._progress_value < 90:
            step = 1 if self._progress_value < 70 else (1 if self._progress_value % 2 == 0 else 0)
            if step:
                self._on_progress(self._progress_value + step)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.canvas.set_interaction_enabled(not busy)

        editable = not busy
        self.btn_fill.setEnabled(editable)
        self.btn_done.setEnabled(editable)
        self.btn_remove.setEnabled(editable and self.canvas.has_selection())
        self.btn_clear_sel.setEnabled(editable and self.canvas.has_selection())
        self.btn_sel_add.setEnabled(editable and self.canvas.has_selection())
        self.btn_sel_subtract.setEnabled(editable and self.canvas.has_selection())
        self.btn_sel_protect.setEnabled(editable and self.canvas.has_selection())
        self.btn_mask_clear.setEnabled(editable and self.canvas.has_active_mask())
        self.radius_slider.setEnabled(editable)
        self.hardness_slider.setEnabled(editable)
        self.opacity_slider.setEnabled(editable)
        self.spacing_slider.setEnabled(editable)
        self.refine_radius.setEnabled(editable)
        self.layer_combo.setEnabled(editable)
        self.ai_name_edit.setEnabled(editable)
        self.btn_ai_run.setEnabled(editable)
        for button in (
            self.btn_layer_add,
            self.btn_layer_protect,
            self.btn_layer_delete,
            self.btn_role_fill,
            self.btn_role_protect,
            self.btn_layer_visible,
            self.btn_mask_invert,
            self.btn_mask_save,
            self.btn_mask_load,
            self.btn_mask_export,
        ):
            button.setEnabled(editable)
        for button in self._refine_buttons.values():
            button.setEnabled(editable)
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

        if busy:
            self.btn_cancel.setText(tr["BgRetouch"].get("StopFill", "Stop"))
            self.progress_panel.setVisible(True)
            self._on_progress(0)
        else:
            self.btn_cancel.setText(tr["BgRetouch"]["Cancel"])
            self._progress_timer.stop()

    def _on_cancel_clicked(self):
        if self._select_busy:
            self.select_controller.cancel()
            return
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
            self._pending_lama_mask = None
            self._set_busy(False)
            self.progress_panel.setVisible(False)

    def reject(self):
        if self._busy:
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
        mask = self.canvas.mask_for_fill()

        if mask is None or not np.any(mask):
            self.status.setText(tr["BgRetouch"]["NoMask"])
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
        diag.run(f"LAMA fill START  mask=fill_region  model={os.path.basename(path)}")
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
                # Keep RGB as written by LAMA (do not re-composite via convert("RGB")).
                rgb_out = np.asarray(rgba)[:, :, :3].copy()
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
                "roi_padding": 128,
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
