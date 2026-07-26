"""Pre-remove protect mask dialog - paint areas to keep opaque after BG remove."""

from __future__ import annotations

import time

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
    QSizePolicy,
)
from qfluentwidgets import MessageBox, BodyLabel, LineEdit

from backend.config import config, tr
from backend.tools import diag
from ui.component.controls.button_styles import make_button, make_toggle_button, paint_toggle_button
from ui.component.controls.slider_styles import PrimarySlider
from ui.component.workspace.editor_page import EditorPage
from ui.component.preview.retouch_canvas import RetouchCanvas, RetouchTool
from ui.component.select_object_controller import SelectObjectController
from ui.theme import DIALOG, FORM, SECTION, TEXT, BG, TEXT_SECONDARY


def _rail_label(text: str, parent: QWidget) -> BodyLabel:
    lbl = BodyLabel(text, parent)
    lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
    return lbl


class BgProtectDialog(QDialog):
    """
    Paint a keep-mask before background removal.

    Painted regions stay opaque after rembg (not cut). Overlay only - never
    baked into the source image RGB.
    """

    finished_mask = Signal(object)  # np.ndarray uint8 L, or None if cleared/cancel path unused

    def __init__(
        self,
        rgba: Image.Image,
        parent=None,
        *,
        initial_mask: np.ndarray | None = None,
    ):
        super().__init__(parent)
        bg = tr["BgProtect"]
        self.setWindowTitle(bg["Title"])
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

        self._pending_rgba = rgba
        self._pending_mask = initial_mask
        self._had_initial_mask = bool(
            initial_mask is not None and np.any(initial_mask)
        )
        self._select_busy = False

        self.select_controller = SelectObjectController(self)
        self.select_controller.busy_changed.connect(self._on_select_busy)
        self.select_controller.failed.connect(self._on_select_failed)
        self.select_controller.finished.connect(self._on_select_finished)
        self.select_controller.status.connect(self._on_select_status)

        self.canvas = RetouchCanvas(self)
        self.canvas.set_tool(RetouchTool.MASK)

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

        # ── Tools: Paint keep / Erase keep ─────────────────────────────
        tools_body = QWidget(rail)
        tools_layout = QVBoxLayout(tools_body)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(SECTION["spacing"])

        self._tool_group = QButtonGroup(self)
        self._tool_buttons, tool_wrap = _grid_buttons(
            tools_body,
            [
                (RetouchTool.SELECT_OBJECT, bg["ToolSelectObject"]),
                (RetouchTool.MASK, bg["ToolPaintKeep"]),
                (RetouchTool.ERASE_MASK, bg["ToolEraseKeep"]),
            ],
            2,
        )
        tools_layout.addWidget(tool_wrap)
        for key, btn in self._tool_buttons.items():
            self._tool_group.addButton(btn)
            btn.clicked.connect(lambda checked=False, k=key: self._select_tool(k))
        tip_map = {
            RetouchTool.SELECT_OBJECT: bg.get("ToolSelectObjectTip", ""),
            RetouchTool.MASK: bg.get("ToolPaintKeepTip", ""),
            RetouchTool.ERASE_MASK: bg.get("ToolEraseKeepTip", ""),
        }
        for key, tip in tip_map.items():
            if tip:
                self._tool_buttons[key].setToolTip(tip)

        obj_wrap = QWidget(tools_body)
        obj_col = QVBoxLayout(obj_wrap)
        obj_col.setContentsMargins(0, 0, 0, 0)
        obj_col.setSpacing(FORM["tight_spacing"])
        obj_col.addWidget(_rail_label(bg["ObjectName"], obj_wrap))
        self.object_name_edit = LineEdit(obj_wrap)
        self.object_name_edit.setPlaceholderText(bg["ObjectNamePlaceholder"])
        self.object_name_edit.returnPressed.connect(self._run_select_from_text)
        obj_col.addWidget(self.object_name_edit)
        self.btn_select_run = make_button(bg["SelectObjectRun"], "primary", obj_wrap)
        self.btn_select_run.clicked.connect(self._run_select_from_text)
        obj_col.addWidget(self.btn_select_run)
        self.btn_select_refine = make_button(
            bg.get("SelectObjectRefine", "Add to mask"), "secondary", obj_wrap
        )
        self.btn_select_refine.setToolTip(
            bg.get(
                "SelectObjectRefineTip",
                "Stay on Select object and click again to add missed areas to the mask layer.",
            )
        )
        self.btn_select_refine.clicked.connect(self._focus_select_object_refine)
        obj_col.addWidget(self.btn_select_refine)
        self.select_status = BodyLabel("", obj_wrap)
        self.select_status.setWordWrap(True)
        self.select_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
        obj_col.addWidget(self.select_status)
        tools_layout.addWidget(obj_wrap)

        hint = bg.get("ObjectMaskWorkflow", "")
        if hint:
            self.object_mask_hint = BodyLabel(hint, tools_body)
            self.object_mask_hint.setWordWrap(True)
            self.object_mask_hint.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
            tools_layout.addWidget(self.object_mask_hint)

        self.editor.add_section(bg["Tools"], tools_body)

        # ── Brush options ──────────────────────────────────────────────
        opts_body = QWidget(rail)
        opts_layout = QVBoxLayout(opts_body)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        opts_layout.setSpacing(SECTION["spacing"])

        size_wrap = QWidget(opts_body)
        size_layout = QVBoxLayout(size_wrap)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(FORM.get("tight_spacing", FORM["field_spacing"]))
        size_header = QHBoxLayout()
        size_header.addWidget(_rail_label(tr["BgRetouch"]["BrushSize"], size_wrap))
        size_layout.addLayout(size_header)
        self.size_slider = PrimarySlider(Qt.Horizontal, size_wrap)
        self.size_slider.setRange(3, 120)
        self.size_slider.setValue(20)
        self.canvas.set_radius(20)
        self.size_slider.valueChanged.connect(self.canvas.set_radius)
        size_layout.addWidget(self.size_slider)
        opts_layout.addWidget(size_wrap)

        hard_wrap = QWidget(opts_body)
        hard_layout = QVBoxLayout(hard_wrap)
        hard_layout.setContentsMargins(0, 0, 0, 0)
        hard_layout.setSpacing(FORM.get("tight_spacing", FORM["field_spacing"]))
        hard_header = QHBoxLayout()
        hard_header.addWidget(_rail_label(tr["BgRetouch"]["BrushHardness"], hard_wrap))
        hard_layout.addLayout(hard_header)
        self.hard_slider = PrimarySlider(Qt.Horizontal, hard_wrap)
        self.hard_slider.setRange(0, 100)
        self.hard_slider.setValue(60)
        self.canvas.set_hardness(60)
        self.hard_slider.valueChanged.connect(self.canvas.set_hardness)
        hard_layout.addWidget(self.hard_slider)
        opts_layout.addWidget(hard_wrap)

        self.editor.add_section(tr["BgRetouch"].get("Brush", "Brush"), opts_body)

        # ── Edit: clear / undo / redo ──────────────────────────────────
        edit_body = QWidget(rail)
        edit_layout = QVBoxLayout(edit_body)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(SECTION["spacing"])

        self.btn_clear = make_button(bg["ClearMask"], "secondary", edit_body)
        self.btn_clear.setToolTip(bg["ClearTip"])
        self.btn_clear.clicked.connect(self._on_clear)
        edit_layout.addWidget(self.btn_clear)

        hist = QHBoxLayout()
        hist.setSpacing(gap)
        self.btn_undo = make_button(tr["BgRetouch"]["Undo"], "secondary", edit_body)
        self.btn_undo.clicked.connect(self.canvas.undo)
        hist.addWidget(self.btn_undo)
        self.btn_redo = make_button(tr["BgRetouch"]["Redo"], "secondary", edit_body)
        self.btn_redo.clicked.connect(self.canvas.redo)
        hist.addWidget(self.btn_redo)
        edit_layout.addLayout(hist)

        self.editor.add_section(tr["BgRetouch"].get("Edit", "Edit"), edit_body)

        # ── Footer actions ─────────────────────────────────────────────
        footer = QWidget(rail)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(SECTION["spacing"])

        self.btn_done = make_button(bg["SaveMask"], "primary", footer)
        self.btn_done.setToolTip(bg.get("SaveMaskTip", ""))
        self.btn_done.clicked.connect(self._on_done)
        footer_layout.addWidget(self.btn_done)

        self.btn_cancel = make_button(tr["BgRetouch"]["Cancel"], "secondary", footer)
        self.btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(self.btn_cancel)

        self.editor.add_rail_stretch(1)
        self.editor.add_section(
            tr["BgRetouch"].get("Actions", "Actions"),
            footer,
        )

        self.canvas.history_changed.connect(self._refresh_history_buttons)
        self.canvas.image_changed.connect(self._refresh_clear_button)
        self.canvas.select_object_clicked.connect(self._on_select_click)
        self._tool_buttons[RetouchTool.MASK].setChecked(True)
        self.select_status.setText(bg.get("StatusPaint", ""))
        self._refresh_history_buttons()
        self._refresh_clear_button()
        # Caller presents the window (present_editor_dialog) - do not show here

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_rgba is not None:
            QTimer.singleShot(0, self._load_pending_image)

    def _load_pending_image(self):
        rgba = self._pending_rgba
        mask = self._pending_mask
        self._pending_rgba = None
        self._pending_mask = None
        if rgba is None:
            return
        t0 = time.perf_counter()
        self.canvas.set_image(rgba)
        if mask is not None:
            self.canvas.set_mask(mask)
        self.canvas.set_tool(RetouchTool.MASK)
        # Small images: prefer ~100% instead of stretching Fit across a huge pane
        iw, ih = rgba.size
        if max(iw, ih) < 900:
            self.canvas.zoom_actual()
        ms = (time.perf_counter() - t0) * 1000.0
        diag.event(f"Edit Keep Mask canvas ready  {iw}x{ih}  {ms:.0f}ms")

    def reject(self):
        diag.event("Edit Keep Mask dialog CANCEL")
        super().reject()

    def _select_tool(self, tool: RetouchTool):
        bg = tr["BgProtect"]
        for k, btn in self._tool_buttons.items():
            btn.setChecked(k == tool)
            paint_toggle_button(btn)
        self.canvas.set_tool(tool)
        if tool == RetouchTool.MASK:
            self.select_status.setText(bg.get("StatusPaint", ""))
        elif tool == RetouchTool.ERASE_MASK:
            self.select_status.setText(bg.get("StatusErase", ""))
        elif tool == RetouchTool.SELECT_OBJECT:
            self.select_status.setText(bg.get("ToolSelectObjectTip", ""))

    def _on_select_busy(self, busy: bool):
        self._select_busy = busy
        self.canvas.set_interaction_enabled(not busy)
        self.btn_select_run.setEnabled(not busy)
        self.object_name_edit.setEnabled(not busy)
        self.btn_done.setEnabled(not busy)
        for btn in self._tool_buttons.values():
            btn.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy and self.canvas.has_painted_mask())
        self.btn_undo.setEnabled(not busy and self.canvas.can_undo())
        self.btn_redo.setEnabled(not busy and self.canvas.can_redo())

    def _on_select_status(self, msg: str):
        self.select_status.setText(msg)

    def _on_select_failed(self, msg: str):
        self.select_status.setText(msg)
        self._alert(tr["SelectObject"]["FailedTitle"], msg)

    def _on_select_finished(self, mask):
        if mask is None:
            return
        self.canvas.union_object_mask(mask)
        self.select_status.setText(tr["BgProtect"]["SelectObjectDone"])
        self._refresh_clear_button()

    def _focus_select_object_refine(self):
        self._select_tool(RetouchTool.SELECT_OBJECT)

    def _on_select_click(self, x: int, y: int):
        if self._select_busy or self.canvas.tool != RetouchTool.SELECT_OBJECT:
            return
        img = self.canvas.get_image()
        if img is None:
            return
        text = self.object_name_edit.text().strip()
        self.select_controller.run(img, click_xy=(x, y), text=text)

    def _run_select_from_text(self):
        if self._select_busy:
            return
        text = self.object_name_edit.text().strip()
        if not text:
            self._alert(
                tr["SelectObject"]["FailedTitle"],
                tr["SelectObject"].get("NeedClickOrText", "Click the object or enter a name."),
            )
            return
        img = self.canvas.get_image()
        if img is None and self._pending_rgba is not None:
            img = self._pending_rgba
        if img is None:
            return
        self.canvas.set_tool(RetouchTool.SELECT_OBJECT)
        for k, btn in self._tool_buttons.items():
            btn.setChecked(k == RetouchTool.SELECT_OBJECT)
            paint_toggle_button(btn)
        self.select_controller.run(img, text=text)

    def _on_clear(self):
        diag.run("Keep Mask clear")
        self.canvas.clear_mask()

    def _refresh_history_buttons(self):
        self.btn_undo.setEnabled(self.canvas.can_undo())
        self.btn_redo.setEnabled(self.canvas.can_redo())

    def _refresh_clear_button(self):
        self.btn_clear.setEnabled(self.canvas.has_painted_mask())

    def _alert(self, title: str, content: str):
        box = MessageBox(title, content, self)
        box.yesButton.hide()
        box.cancelButton.setText(tr["Common"].get("OK", "OK"))
        box.buttonLayout.insertStretch(0, 1)
        box.exec()

    def _on_done(self):
        mask = self.canvas.get_mask()
        empty = mask is None or not np.any(mask)
        if empty:
            if self._had_initial_mask:
                # Allow clearing a previously saved keep mask
                diag.event("Edit Keep Mask dialog DONE  cleared")
                self.finished_mask.emit(None)
                self.accept()
                return
            self._alert(
                tr["BgRemove"]["ProtectMaskEmptyTitle"],
                tr["BgRemove"]["ProtectMaskEmpty"],
            )
            return
        pixels = int(np.count_nonzero(mask))
        diag.event(f"Edit Keep Mask dialog DONE  painted_px={pixels}")
        self.finished_mask.emit(mask)
        self.accept()
