"""Paint canvas for BG retouch: brush, lasso/pen/rect selection, undo, zoom."""

from __future__ import annotations

from enum import Enum, unique
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, Signal, QPoint, QEvent, QTimer
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QCursor, QWheelEvent, QKeyEvent,
    QKeySequence, QShortcut, QPolygon,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QSizePolicy, QFrame,
)
from backend.config import config
from backend.media.mask_layers import MaskLayer, MaskLayerStack
from ui.component.preview.zoom_chrome import ZoomChromeBar
from ui.component.preview.zoomable_image_view import checkerboard_pixmap_from_rgba
from ui.theme import DARK_BG, FORM, PRIMARY


@unique
class RetouchTool(Enum):
    MASK = "mask"
    ERASE_MASK = "erase_mask"
    ERASE_ALPHA = "erase_alpha"
    RESTORE_ALPHA = "restore_alpha"
    LASSO = "lasso"
    PEN = "pen"
    RECT = "rect"
    SELECT_OBJECT = "select_object"


_SELECT_TOOLS = frozenset({
    RetouchTool.LASSO,
    RetouchTool.PEN,
    RetouchTool.RECT,
    RetouchTool.SELECT_OBJECT,
})

_ALPHA_TOOLS = frozenset({
    RetouchTool.ERASE_ALPHA,
    RetouchTool.RESTORE_ALPHA,
})

_PRIMARY_RGB = tuple(int(PRIMARY[i : i + 2], 16) for i in (1, 3, 5))  # #RRGGBB
PATH_COLOR = QColor(*_PRIMARY_RGB, 230)
SELECTION_PRIMARY = _PRIMARY_RGB


@lru_cache(maxsize=64)
def _brush_kernel(radius: int, hardness_q: int) -> np.ndarray:
    """
    Circular brush kernel (uint8 0–255).

    hardness_q: hardness * 1000 (quantized for cache). 0 = soft, 1000 = hard.
    """
    r = max(1, int(radius))
    h = float(np.clip(hardness_q / 1000.0, 0.0, 1.0))
    yy, xx = np.ogrid[-r : r + 1, -r : r + 1]
    dist = np.sqrt(xx * xx + yy * yy).astype(np.float32)

    if h >= 0.999:
        return (dist <= r).astype(np.uint8) * 255

    core = h * r
    t = np.ones_like(dist)
    feather = dist > core
    span = max(1e-6, r - core)
    t[feather] = np.clip(1.0 - (dist[feather] - core) / span, 0.0, 1.0)
    soft = 0.5 - 0.5 * np.cos(np.pi * t)
    soft[dist > r] = 0.0
    return (soft * 255.0).astype(np.uint8)


def _kernel(radius: int, hardness: float) -> np.ndarray:
    return _brush_kernel(max(1, int(radius)), int(round(float(hardness) * 1000)))


class RetouchCanvas(QWidget):
    """Fullscreen-friendly image editor with soft brush + selection tools + undo."""

    image_changed = Signal()
    history_changed = Signal()  # undo/redo availability changed
    selection_changed = Signal()
    layers_changed = Signal()
    select_object_clicked = Signal(int, int)  # image x, y

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._rgba: Image.Image | None = None
        # Mutable RGBA during alpha brush strokes (avoids Image.copy every stamp)
        self._rgba_arr: np.ndarray | None = None
        # Source image before BG removal - used by Restore to bring pixels back
        self._original: Image.Image | None = None
        self._original_arr: np.ndarray | None = None
        self._mask_stack: MaskLayerStack | None = None
        # Active layer alias retained for the hot brush-stamping path.
        self._mask: np.ndarray | None = None
        self._tool = RetouchTool.ERASE_ALPHA  # default: Photoshop-like eraser
        self._radius = 20
        self._hardness = 0.85  # 0 soft … 1 hard
        self._opacity = 1.0
        self._spacing = 0.33
        self._zoom = 1.0
        self._fit_mode = True
        self._painting = False
        self._stroke_dirty = False
        self._stroke_last: tuple[int, int] | None = None
        self._panning = False
        self._pan_last: QPoint | None = None
        self._space_down = False
        self._interaction_enabled = True
        self._display: QPixmap | None = None
        self._base_checker: QPixmap | None = None
        self._undo: list[
            tuple[Image.Image, list[MaskLayer], int, np.ndarray | None]
        ] = []
        self._redo: list[
            tuple[Image.Image, list[MaskLayer], int, np.ndarray | None]
        ] = []
        self._cursor_cache_key: tuple | None = None
        self._cursor_cache: QCursor | None = None

        # Selection (Lasso / Pen / Rect)
        self._sel_points: list[tuple[int, int]] = []
        self._selection: np.ndarray | None = None
        self._selecting = False  # lasso/rect drag in progress
        self._rect_origin: tuple[int, int] | None = None

        # Coalesce expensive display rebuilds while dragging
        self._refresh_pending = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._flush_refresh)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(FORM["tight_spacing"])

        self.zoom_chrome = ZoomChromeBar(self)
        self.zoom_chrome.zoom_out_clicked.connect(self.zoom_out)
        self.zoom_chrome.zoom_in_clicked.connect(self.zoom_in)
        self.zoom_chrome.zoom_fit_clicked.connect(self.zoom_fit)
        self.zoom_chrome.zoom_actual_clicked.connect(self.zoom_actual)
        self.zoom_label = self.zoom_chrome.zoom_label  # back-compat for label updates
        root.addWidget(self.zoom_chrome)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background: {DARK_BG}; border: none; }}"
        )
        self.scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.scroll.viewport().setStyleSheet(f"background: {DARK_BG}; border: none;")
        self.scroll.viewport().setMouseTracking(True)

        self.image_label = QLabel("")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        self.image_label.setMouseTracking(True)
        self.scroll.setWidget(self.image_label)
        root.addWidget(self.scroll, 1)

        self.scroll.viewport().installEventFilter(self)
        self.image_label.installEventFilter(self)

        sc_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        sc_undo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_undo.activated.connect(self.undo)
        sc_redo = QShortcut(QKeySequence.StandardKey.Redo, self)
        sc_redo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_redo.activated.connect(self.redo)
        sc_redo_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        sc_redo_y.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_redo_y.activated.connect(self.redo)

    # --- public API ---

    @property
    def tool(self) -> RetouchTool:
        return self._tool

    def is_select_tool(self) -> bool:
        return self._tool in _SELECT_TOOLS

    def set_tool(self, tool: RetouchTool):
        prev = self._tool
        self._tool = tool
        self._cursor_cache_key = None
        # Switching away from a select tool cancels in-progress path only
        if prev in _SELECT_TOOLS and tool != prev:
            self._cancel_in_progress_path(refresh=True)
        self._update_cursor()

    def set_interaction_enabled(self, enabled: bool):
        """Lock painting / selection while Fill (or other jobs) run."""
        enabled = bool(enabled)
        if enabled == self._interaction_enabled:
            return
        self._interaction_enabled = enabled
        if not enabled:
            # Abort any in-progress stroke / path without committing more work
            self._painting = False
            self._stroke_last = None
            self._panning = False
            self._pan_last = None
            self._cancel_in_progress_path(refresh=False)
        self._update_cursor()

    def interaction_enabled(self) -> bool:
        return self._interaction_enabled

    def set_radius(self, radius: int):
        self._radius = max(1, int(radius))
        self._cursor_cache_key = None
        self._update_cursor()

    def radius(self) -> int:
        return self._radius

    def set_hardness(self, hardness: float):
        """hardness 0–100 (UI) or 0–1."""
        h = float(hardness)
        if h > 1.0:
            h = h / 100.0
        self._hardness = max(0.0, min(1.0, h))
        self._cursor_cache_key = None
        self._update_cursor()

    def hardness(self) -> float:
        return self._hardness

    def set_opacity(self, opacity: float):
        value = float(opacity)
        if value > 1.0:
            value /= 100.0
        self._opacity = max(0.01, min(1.0, value))

    def opacity(self) -> float:
        return self._opacity

    def set_spacing(self, spacing: float):
        """Brush spacing as 1–100 percent of diameter."""
        value = float(spacing)
        if value > 1.0:
            value /= 100.0
        self._spacing = max(0.01, min(1.0, value))

    def spacing(self) -> float:
        return self._spacing

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def has_selection(self) -> bool:
        return self._selection is not None and bool(np.any(self._selection))

    def has_painted_mask(self) -> bool:
        mask = self.get_mask()
        return mask is not None and bool(np.any(mask))

    def has_active_mask(self) -> bool:
        return self._mask is not None and bool(np.any(self._mask))

    def layer_descriptions(self) -> list[str]:
        if self._mask_stack is None:
            return []
        return [
            f"{'Protect' if layer.protect else 'Fill'} · {layer.name}"
            for layer in self._mask_stack.layers
        ]

    def active_layer_index(self) -> int:
        return self._mask_stack.active_index if self._mask_stack is not None else 0

    def set_active_layer(self, index: int):
        if self._mask_stack is None:
            return
        self._mask_stack.set_active(index)
        self._sync_active_mask()
        self._refresh_display(immediate=True)
        self.layers_changed.emit()

    def add_mask_layer(self, *, protect: bool = False, name: str | None = None):
        if self._mask_stack is None:
            return
        self._push_undo()
        self._mask_stack.add_layer(name=name, protect=protect)
        self._sync_active_mask()
        self._refresh_display(immediate=True)
        self.layers_changed.emit()
        self.image_changed.emit()

    def remove_active_layer(self):
        if self._mask_stack is None:
            return
        self._push_undo()
        self._mask_stack.remove_active()
        self._sync_active_mask()
        self._refresh_display(immediate=True)
        self.layers_changed.emit()
        self.image_changed.emit()

    def set_active_layer_protect(self, protect: bool):
        if self._mask_stack is None:
            return
        if self._mask_stack.active.protect == bool(protect):
            return
        self._push_undo()
        self._mask_stack.set_active_protect(protect)
        self._refresh_display(immediate=True)
        self.layers_changed.emit()
        self.image_changed.emit()

    def active_layer_is_protect(self) -> bool:
        return bool(self._mask_stack and self._mask_stack.active.protect)

    def set_active_layer_visible(self, visible: bool):
        if self._mask_stack is None:
            return
        visible = bool(visible)
        if self._mask_stack.active.visible == visible:
            return
        self._push_undo()
        self._mask_stack.active.visible = visible
        self._refresh_display(immediate=True)
        self.layers_changed.emit()
        self.image_changed.emit()

    def active_layer_is_visible(self) -> bool:
        return bool(self._mask_stack and self._mask_stack.active.visible)

    def _sync_active_mask(self):
        self._mask = (
            self._mask_stack.active.mask if self._mask_stack is not None else None
        )

    def _normalize_mask_to_canvas(self, mask: np.ndarray) -> np.ndarray | None:
        if self._mask is None or mask is None:
            return None
        h, w = self._mask.shape[:2]
        arr = np.asarray(mask)
        if arr.ndim != 2:
            return None
        if arr.shape[:2] != (h, w):
            arr = np.asarray(
                Image.fromarray(arr.astype(np.uint8), mode="L").resize(
                    (w, h), Image.Resampling.BILINEAR
                )
            )
        return (arr > 32).astype(np.uint8) * 255

    def union_object_mask(self, mask: np.ndarray):
        """Add SAM2 / Select Object result to the working mask layer (overlay only)."""
        arr = self._normalize_mask_to_canvas(mask)
        if arr is None:
            return
        self._push_undo()
        np.maximum(self._mask, arr, out=self._mask)
        self.clear_selection()
        self._refresh_display(immediate=True)
        self.image_changed.emit()

    def mask_for_fill(self) -> np.ndarray | None:
        """Visible fill layers plus selection, minus every visible protect layer."""
        painted = self.get_fill_mask()
        protected = self.get_protect_mask()
        sel = self.selection_as_mask()
        if painted is None and sel is None:
            return None
        if painted is None:
            combined = sel.copy()
        else:
            combined = painted.copy()
            if sel is not None and np.any(sel):
                np.maximum(combined, sel, out=combined)
        if protected is not None and np.any(protected):
            combined = np.maximum(
                0,
                combined.astype(np.int16) - protected.astype(np.int16),
            ).astype(np.uint8)
        return combined if np.any(combined) else None

    def clear_selection(self):
        had = self.has_selection() or bool(self._sel_points) or self._rect_origin is not None
        self._selection = None
        self._sel_points.clear()
        self._rect_origin = None
        self._selecting = False
        if had:
            self._refresh_display(immediate=True)
            self.selection_changed.emit()

    def selection_as_mask(self) -> np.ndarray | None:
        """Copy of closed selection for LAMA (255 inside), or None."""
        if not self.has_selection():
            return None
        return self._selection.copy()

    def apply_selection_to_mask(self, operation: str):
        if (
            not self.has_selection()
            or self._selection is None
            or self._mask is None
            or self._mask_stack is None
        ):
            return
        self._push_undo()
        if operation == "add":
            np.maximum(self._mask, self._selection, out=self._mask)
        elif operation == "subtract":
            reduced = np.maximum(
                0,
                self._mask.astype(np.int16)
                - self._selection.astype(np.int16),
            )
            self._mask[:] = reduced.astype(np.uint8)
        elif operation == "protect":
            self._mask_stack.set_active_protect(True)
            np.maximum(self._mask, self._selection, out=self._mask)
        else:
            raise ValueError(f"unknown selection mask operation: {operation}")
        self._selection = None
        self._sel_points.clear()
        self._rect_origin = None
        self._selecting = False
        self._refresh_display(immediate=True)
        self.selection_changed.emit()
        self.layers_changed.emit()
        self.image_changed.emit()

    def remove_selection(self):
        """Erase alpha inside closed selection, then clear selection."""
        if not self.has_selection() or self._rgba is None or self._selection is None:
            return
        self._commit_rgba_arr()
        self._push_undo()
        arr = np.asarray(self._rgba).copy()
        m = self._selection > 0
        arr[m, 3] = 0
        self._rgba = Image.fromarray(arr, "RGBA")
        self._rgba_arr = None
        self._base_checker = None
        self._selection = None
        self._sel_points.clear()
        self._rect_origin = None
        self._selecting = False
        self._refresh_display(immediate=True)
        self.selection_changed.emit()
        self.image_changed.emit()

    def set_image(self, rgba: Image.Image, original: Image.Image | None = None):
        self._rgba = rgba.convert("RGBA")
        self._rgba_arr = None
        w, h = self._rgba.size
        if original is not None:
            src = original.convert("RGBA")
            if src.size != (w, h):
                # Align restore source to canvas size (canvas stays at uploaded WxH)
                src = src.resize((w, h), Image.Resampling.LANCZOS)
            self._original = src
        else:
            # Fallback: current image (restore still works for erased subject)
            self._original = self._rgba.copy()
        self._original_arr = None  # lazy - built on first Restore stamp
        self._mask_stack = MaskLayerStack(w, h)
        self._sync_active_mask()
        self._selection = None
        self._sel_points.clear()
        self._rect_origin = None
        self._selecting = False
        self._stroke_last = None
        self._fit_mode = True
        self._base_checker = None
        self._cursor_cache_key = None
        self._undo.clear()
        self._redo.clear()
        self._refresh_display(immediate=True)
        self.zoom_fit()
        self._update_cursor()
        self.history_changed.emit()
        self.selection_changed.emit()
        self.layers_changed.emit()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def get_image(self) -> Image.Image | None:
        self._commit_rgba_arr()
        return self._rgba.copy() if self._rgba else None

    def get_original(self) -> Image.Image | None:
        """Pre-retouch / pre-rembg source used for Restore and LAMA context."""
        return self._original.copy() if self._original is not None else None

    def get_mask(self) -> np.ndarray | None:
        if self._mask_stack is None:
            return None
        return self._mask_stack.composite()

    def get_fill_mask(self) -> np.ndarray | None:
        if self._mask_stack is None:
            return None
        return self._mask_stack.fill_mask()

    def get_protect_mask(self) -> np.ndarray | None:
        if self._mask_stack is None:
            return None
        return self._mask_stack.protect_mask()

    def set_mask(self, mask: np.ndarray | None):
        """Replace painted mask (resized to image size). Does not push undo."""
        if self._rgba is None or self._mask is None or self._mask_stack is None:
            return
        self._commit_rgba_arr()
        h, w = self._mask.shape[:2]
        if mask is None:
            self._mask_stack.clear_all()
        else:
            arr = np.asarray(mask)
            if arr.ndim != 2:
                raise ValueError("mask must be 2D uint8")
            if arr.shape[:2] != (h, w):
                arr = np.asarray(
                    Image.fromarray(arr.astype(np.uint8), mode="L").resize(
                        (w, h), Image.Resampling.BILINEAR
                    )
                )
            self._mask_stack = MaskLayerStack(w, h)
            self._mask_stack.active.mask[:] = arr.astype(np.uint8, copy=False)
            self._sync_active_mask()
        self._undo.clear()
        self._redo.clear()
        self._refresh_display(immediate=True)
        self.history_changed.emit()
        self.layers_changed.emit()
        self.image_changed.emit()

    def clear_mask(self):
        if self._mask is None or not np.any(self._mask):
            return
        self._push_undo()
        if self._mask_stack is not None:
            self._mask_stack.clear_active()
        self._refresh_display(immediate=True)
        self.image_changed.emit()

    def invert_mask(self):
        if self._mask_stack is None:
            return
        self._push_undo()
        self._mask_stack.invert_active()
        self._refresh_display(immediate=True)
        self.image_changed.emit()

    def refine_mask(self, operation: str, radius: int = 3):
        if self._mask_stack is None or self._rgba is None:
            return
        self._commit_rgba_arr()
        self._push_undo()
        guide = np.asarray(self._rgba)
        self._mask_stack.transform_active(
            operation,
            radius=radius,
            guide_rgba=guide,
        )
        self._refresh_display(immediate=True)
        self.image_changed.emit()

    def save_mask_layers(self, path: str):
        if self._mask_stack is None:
            raise ValueError("no mask canvas is loaded")
        self._mask_stack.save(path)

    def load_mask_layers(self, path: str):
        if self._rgba is None:
            return
        loaded = MaskLayerStack.load(path)
        if (loaded.width, loaded.height) != self._rgba.size:
            raise ValueError("mask project dimensions do not match the image")
        self._push_undo()
        self._mask_stack = loaded
        self._sync_active_mask()
        self.clear_selection()
        self._refresh_display(immediate=True)
        self.layers_changed.emit()
        self.image_changed.emit()

    def apply_rgb_patch(self, rgb: np.ndarray, mask: np.ndarray):
        if self._rgba is None:
            return
        self._commit_rgba_arr()
        self._push_undo()
        arr = np.asarray(self._rgba).copy()
        m = mask > 0
        blend = (mask.astype(np.float32) / 255.0)[..., np.newaxis]
        current_rgb = arr[:, :, :3].astype(np.float32)
        result_rgb = np.asarray(rgb)[:, :, :3].astype(np.float32)
        arr[:, :, :3] = np.clip(
            current_rgb * (1.0 - blend) + result_rgb * blend,
            0,
            255,
        ).astype(np.uint8)
        alpha = arr[:, :, 3].astype(np.float32)
        arr[:, :, 3] = np.where(
            m,
            np.clip(alpha + (255.0 - alpha) * blend[:, :, 0], 0, 255),
            alpha,
        ).astype(np.uint8)
        self._rgba = Image.fromarray(arr, "RGBA")
        self._rgba_arr = None
        if self._mask_stack is not None:
            self._mask_stack.clear_all()
            self._sync_active_mask()
        self._base_checker = None
        # Selection was used as LAMA region - clear it
        self._selection = None
        self._sel_points.clear()
        self._refresh_display(immediate=True)
        self.selection_changed.emit()
        self.layers_changed.emit()
        self.image_changed.emit()

    def undo(self):
        if not self._interaction_enabled:
            return
        if (
            not self._undo
            or self._rgba is None
            or self._mask is None
            or self._mask_stack is None
        ):
            return
        self._commit_rgba_arr()
        self._redo.append(self._history_snapshot())
        rgba, layers, active, selection = self._undo.pop()
        self._rgba = rgba
        self._rgba_arr = None
        self._mask_stack.restore(layers, active)
        self._sync_active_mask()
        self._selection = None if selection is None else selection.copy()
        self._base_checker = None
        self._refresh_display(immediate=True)
        self.history_changed.emit()
        self.selection_changed.emit()
        self.layers_changed.emit()
        self.image_changed.emit()

    def redo(self):
        if not self._interaction_enabled:
            return
        if (
            not self._redo
            or self._rgba is None
            or self._mask is None
            or self._mask_stack is None
        ):
            return
        self._commit_rgba_arr()
        self._undo.append(self._history_snapshot())
        rgba, layers, active, selection = self._redo.pop()
        self._rgba = rgba
        self._rgba_arr = None
        self._mask_stack.restore(layers, active)
        self._sync_active_mask()
        self._selection = None if selection is None else selection.copy()
        self._base_checker = None
        self._refresh_display(immediate=True)
        self.history_changed.emit()
        self.selection_changed.emit()
        self.layers_changed.emit()
        self.image_changed.emit()

    def _history_snapshot(
        self,
    ) -> tuple[Image.Image, list[MaskLayer], int, np.ndarray | None]:
        assert self._rgba is not None
        assert self._mask_stack is not None
        selection = None if self._selection is None else self._selection.copy()
        return (
            self._rgba.copy(),
            self._mask_stack.clone_layers(),
            self._mask_stack.active_index,
            selection,
        )

    def _push_undo(self):
        if self._rgba is None or self._mask is None or self._mask_stack is None:
            return
        self._commit_rgba_arr()
        self._undo.append(self._history_snapshot())
        if len(self._undo) > config.retouchMaxHistory:
            self._undo.pop(0)
        self._redo.clear()
        self.history_changed.emit()

    def _ensure_rgba_arr(self) -> np.ndarray | None:
        if self._rgba is None:
            return None
        if self._rgba_arr is None:
            self._rgba_arr = np.asarray(self._rgba).copy()
        return self._rgba_arr

    def _ensure_original_arr(self) -> np.ndarray | None:
        if self._original is None:
            return None
        if self._original_arr is None:
            self._original_arr = np.asarray(self._original)
        return self._original_arr

    def _commit_rgba_arr(self):
        """Flush mutable stroke buffer back into the PIL image."""
        if self._rgba_arr is not None:
            self._rgba = Image.fromarray(self._rgba_arr, "RGBA")
            self._rgba_arr = None

    # --- selection helpers ---

    def _cancel_in_progress_path(self, refresh: bool = False):
        had = bool(self._sel_points) or self._rect_origin is not None or self._selecting
        self._sel_points.clear()
        self._rect_origin = None
        self._selecting = False
        if had and refresh:
            self._refresh_display(immediate=True)

    def _rasterize_polygon(self, points: list[tuple[int, int]]) -> np.ndarray | None:
        if self._rgba is None or len(points) < 3:
            return None
        w, h = self._rgba.size
        img = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(img)
        # PIL expects flat list of (x, y)
        draw.polygon(points, outline=255, fill=255)
        return np.asarray(img, dtype=np.uint8)

    def _commit_selection(self, points: list[tuple[int, int]]):
        sel = self._rasterize_polygon(points)
        self._sel_points.clear()
        self._rect_origin = None
        self._selecting = False
        if sel is None or not np.any(sel):
            self._refresh_display(immediate=True)
            return
        self._selection = sel
        self._refresh_display(immediate=True)
        self.selection_changed.emit()

    def _close_pen_path(self):
        if self._tool != RetouchTool.PEN:
            return
        if len(self._sel_points) >= 3:
            self._commit_selection(list(self._sel_points))
        else:
            self._cancel_in_progress_path(refresh=True)

    def _near_first_point(self, pt: tuple[int, int]) -> bool:
        if not self._sel_points:
            return False
        x0, y0 = self._sel_points[0]
        dx = pt[0] - x0
        dy = pt[1] - y0
        return (dx * dx + dy * dy) <= (config.retouchPenCloseRadius * config.retouchPenCloseRadius)

    # --- keys / mouse ---

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = True
            self._update_cursor()
            event.accept()
            return
        if self._tool == RetouchTool.PEN and not event.isAutoRepeat():
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._close_pen_path()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_in_progress_path(refresh=True)
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape and self.is_select_tool():
            self._cancel_in_progress_path(refresh=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = False
            self._update_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _want_pan(self) -> bool:
        """Space+drag pans (no dedicated Pan tool)."""
        return self._space_down

    def _event_label_pos(self, obj, event) -> QPoint | None:
        if obj is self.image_label:
            return event.position().toPoint()
        if obj is self.scroll.viewport():
            return self.image_label.mapFromGlobal(event.globalPosition().toPoint())
        return None

    def eventFilter(self, obj, event):
        et = event.type()

        if et == QEvent.Type.Wheel and obj in (self.scroll.viewport(), self.image_label):
            # Zoom still allowed while locked (view only)
            self._handle_wheel(event)
            return True

        if self._rgba is None:
            return super().eventFilter(obj, event)

        if obj not in (self.image_label, self.scroll.viewport()):
            return super().eventFilter(obj, event)

        left = Qt.MouseButton.LeftButton

        # While Fill/model runs: block paint, erase, lasso, mask, selection
        if not self._interaction_enabled:
            if et in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonRelease,
            ):
                # Allow space+pan only so user can look around while waiting
                if et == QEvent.Type.MouseButtonPress and event.button() == left and self._want_pan():
                    self._panning = True
                    self._pan_last = event.globalPosition().toPoint()
                    cur = Qt.CursorShape.ClosedHandCursor
                    self.image_label.setCursor(cur)
                    self.scroll.viewport().setCursor(cur)
                    return True
                if et == QEvent.Type.MouseMove and self._panning and self._pan_last is not None:
                    pos = event.globalPosition().toPoint()
                    delta = pos - self._pan_last
                    self._pan_last = pos
                    self.scroll.horizontalScrollBar().setValue(
                        self.scroll.horizontalScrollBar().value() - delta.x()
                    )
                    self.scroll.verticalScrollBar().setValue(
                        self.scroll.verticalScrollBar().value() - delta.y()
                    )
                    return True
                if et == QEvent.Type.MouseButtonRelease and event.button() == left:
                    self._panning = False
                    self._pan_last = None
                    self._update_cursor()
                    return True
                return True
            return super().eventFilter(obj, event)

        if et == QEvent.Type.MouseButtonDblClick and event.button() == left:
            if self._tool == RetouchTool.PEN and not self._want_pan():
                self._close_pen_path()
                return True
            return False

        if et == QEvent.Type.MouseButtonPress and event.button() == left:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            pos = self._event_label_pos(obj, event)
            if pos is None:
                return False
            if self._want_pan():
                self._panning = True
                self._pan_last = event.globalPosition().toPoint()
                cur = Qt.CursorShape.ClosedHandCursor
                self.image_label.setCursor(cur)
                self.scroll.viewport().setCursor(cur)
                return True

            if self.is_select_tool():
                if self._tool == RetouchTool.SELECT_OBJECT:
                    pt = self._label_to_image(pos)
                    if pt is not None:
                        self.select_object_clicked.emit(pt[0], pt[1])
                    return True
                return self._select_press(pos)

            # Brush stroke - snapshot once before painting
            self._push_undo()
            self._painting = True
            self._stroke_dirty = False
            self._stroke_last = None
            if self._tool in _ALPHA_TOOLS:
                self._ensure_rgba_arr()
            self._paint_at(pos)
            return True

        if et == QEvent.Type.MouseMove:
            if self._panning and self._pan_last is not None:
                pos = event.globalPosition().toPoint()
                delta = pos - self._pan_last
                self._pan_last = pos
                self.scroll.horizontalScrollBar().setValue(
                    self.scroll.horizontalScrollBar().value() - delta.x()
                )
                self.scroll.verticalScrollBar().setValue(
                    self.scroll.verticalScrollBar().value() - delta.y()
                )
                return True
            if self._painting:
                pos = self._event_label_pos(obj, event)
                if pos is not None:
                    self._paint_stroke_to(pos)
                return True
            if self._selecting or (
                self._tool == RetouchTool.LASSO and self._sel_points
            ):
                pos = self._event_label_pos(obj, event)
                if pos is not None:
                    self._select_move(pos)
                return True
            return False

        if et == QEvent.Type.MouseButtonRelease and event.button() == left:
            was_paint = self._painting
            was_select = self._selecting or (
                self._tool == RetouchTool.LASSO and bool(self._sel_points)
            )
            self._painting = False
            self._stroke_last = None
            self._panning = False
            self._pan_last = None
            self._update_cursor()
            if was_paint:
                if self._tool in _ALPHA_TOOLS and self._stroke_dirty:
                    self._commit_rgba_arr()
                    self._base_checker = None
                self._refresh_display(immediate=True)
                if not self._stroke_dirty and self._undo:
                    self._undo.pop()
                    self.history_changed.emit()
                else:
                    self.image_changed.emit()
                return True
            if was_select and self.is_select_tool():
                if self._tool == RetouchTool.SELECT_OBJECT:
                    return True
                pos = self._event_label_pos(obj, event)
                self._select_release(pos)
                return True
            return True

        return super().eventFilter(obj, event)

    def _select_press(self, pos: QPoint) -> bool:
        pt = self._label_to_image(pos)
        if pt is None:
            return True

        if self._tool == RetouchTool.LASSO:
            self._sel_points = [pt]
            self._selecting = True
            self._refresh_display(immediate=True)
            return True

        if self._tool == RetouchTool.RECT:
            self._rect_origin = pt
            self._sel_points = [pt, pt]
            self._selecting = True
            self._refresh_display(immediate=True)
            return True

        if self._tool == RetouchTool.PEN:
            if self._sel_points and self._near_first_point(pt) and len(self._sel_points) >= 3:
                self._close_pen_path()
                return True
            self._sel_points.append(pt)
            self._refresh_display(immediate=True)
            return True

        return True

    def _select_move(self, pos: QPoint):
        pt = self._label_to_image(pos)
        if pt is None:
            return

        if self._tool == RetouchTool.LASSO and self._selecting:
            # Avoid flooding with duplicate points
            if not self._sel_points or self._sel_points[-1] != pt:
                self._sel_points.append(pt)
                self._refresh_display()
            return

        if self._tool == RetouchTool.RECT and self._selecting and self._rect_origin is not None:
            self._sel_points = [self._rect_origin, pt]
            self._refresh_display()

    def _select_release(self, pos: QPoint | None):
        if self._tool == RetouchTool.LASSO:
            self._selecting = False
            if len(self._sel_points) >= 3:
                self._commit_selection(list(self._sel_points))
            else:
                self._cancel_in_progress_path(refresh=True)
            return

        if self._tool == RetouchTool.RECT:
            self._selecting = False
            if self._rect_origin is None:
                self._cancel_in_progress_path(refresh=True)
                return
            end = self._label_to_image(pos) if pos is not None else None
            if end is None and len(self._sel_points) >= 2:
                end = self._sel_points[-1]
            if end is None:
                self._cancel_in_progress_path(refresh=True)
                return
            x0, y0 = self._rect_origin
            x1, y1 = end
            if abs(x1 - x0) < 1 and abs(y1 - y0) < 1:
                self._cancel_in_progress_path(refresh=True)
                return
            # Axis-aligned rectangle as 4-point polygon
            left, right = min(x0, x1), max(x0, x1)
            top, bottom = min(y0, y1), max(y0, y1)
            pts = [
                (left, top),
                (right, top),
                (right, bottom),
                (left, bottom),
            ]
            self._commit_selection(pts)
            return

        # Pen: release does nothing (click adds anchors)

    def _shown_pixmap(self) -> QPixmap | None:
        return self.image_label.pixmap()

    def _label_to_image(self, pos: QPoint) -> tuple[int, int] | None:
        if self._rgba is None:
            return None
        pm = self._shown_pixmap()
        if pm is None or pm.isNull():
            return None
        lw, lh = self.image_label.width(), self.image_label.height()
        dw, dh = pm.width(), pm.height()
        ox = (lw - dw) // 2
        oy = (lh - dh) // 2
        x = pos.x() - ox
        y = pos.y() - oy
        if x < 0 or y < 0 or x >= dw or y >= dh:
            return None
        iw, ih = self._rgba.size
        ix = min(iw - 1, max(0, int(x * iw / dw)))
        iy = min(ih - 1, max(0, int(y * ih / dh)))
        return ix, iy

    def _paint_stroke_to(self, pos: QPoint):
        """Stamp brush along the path from last image point to current (smooth stroke)."""
        pt = self._label_to_image(pos)
        if pt is None:
            return
        if self._stroke_last is None:
            self._stamp_brush(pt[0], pt[1])
            self._stroke_last = pt
            self._refresh_display()
            return
        x0, y0 = self._stroke_last
        x1, y1 = pt
        dist = max(abs(x1 - x0), abs(y1 - y0))
        # User-controlled spacing is a fraction of brush diameter.
        step = max(1, int(round(self._radius * 2 * self._spacing)))
        if dist <= step:
            self._stamp_brush(x1, y1)
            self._stroke_last = pt
            self._refresh_display()
            return
        n = int(np.ceil(dist / step))
        for i in range(1, n + 1):
            t = i / n
            ix = int(round(x0 + (x1 - x0) * t))
            iy = int(round(y0 + (y1 - y0) * t))
            self._stamp_brush(ix, iy)
        self._stroke_last = pt
        self._refresh_display()

    def _paint_at(self, pos: QPoint):
        pt = self._label_to_image(pos)
        if pt is None:
            return
        self._stamp_brush(pt[0], pt[1])
        self._stroke_last = pt
        self._refresh_display()

    def _stamp_brush(self, ix: int, iy: int):
        """Stamp onto full-resolution mask/RGBA. Does not refresh the viewport."""
        if self._mask is None or self._rgba is None:
            return
        brush = _kernel(self._radius, self._hardness)
        if self._opacity < 0.999:
            brush = np.clip(
                brush.astype(np.float32) * self._opacity, 0, 255
            ).astype(np.uint8)
        r = self._radius
        h, w = self._mask.shape
        y0, y1 = max(0, iy - r), min(h, iy + r + 1)
        x0, x1 = max(0, ix - r), min(w, ix + r + 1)
        dy0, dy1 = y0 - (iy - r), y1 - (iy - r)
        dx0, dx1 = x0 - (ix - r), x1 - (ix - r)
        kernel = brush[dy0:dy1, dx0:dx1]
        if kernel.size == 0:
            return

        if self._tool == RetouchTool.MASK:
            patch = self._mask[y0:y1, x0:x1]
            np.maximum(patch, kernel, out=patch)
            self._stroke_dirty = True
        elif self._tool == RetouchTool.ERASE_MASK:
            patch = self._mask[y0:y1, x0:x1]
            reduced = np.maximum(0, patch.astype(np.int16) - kernel.astype(np.int16))
            patch[:] = reduced.astype(np.uint8)
            self._stroke_dirty = True
        elif self._tool == RetouchTool.ERASE_ALPHA:
            arr = self._ensure_rgba_arr()
            if arr is None:
                return
            a = arr[y0:y1, x0:x1, 3].astype(np.int16)
            a = np.maximum(0, a - kernel.astype(np.int16))
            arr[y0:y1, x0:x1, 3] = a.astype(np.uint8)
            self._base_checker = None
            self._stroke_dirty = True
        elif self._tool == RetouchTool.RESTORE_ALPHA:
            src = self._ensure_original_arr()
            if src is None:
                return
            arr = self._ensure_rgba_arr()
            if arr is None:
                return
            t = kernel.astype(np.float32) / 255.0
            patch = arr[y0:y1, x0:x1].astype(np.float32)
            orig = src[y0:y1, x0:x1].astype(np.float32)
            t4 = t[..., np.newaxis]
            blended = patch * (1.0 - t4) + orig * t4
            arr[y0:y1, x0:x1] = np.clip(blended, 0, 255).astype(np.uint8)
            self._base_checker = None
            self._stroke_dirty = True

    def _draw_overlay_mask(
        self,
        painter: QPainter,
        mask: np.ndarray,
        base_w: int,
        base_h: int,
        rgb: tuple[int, int, int],
        max_alpha: int,
    ):
        mh, mw = mask.shape[:2]
        if (mw, mh) != (base_w, base_h):
            mask_img = Image.fromarray(mask, mode="L").resize(
                (base_w, base_h), Image.Resampling.BILINEAR
            )
            mask_a = np.ascontiguousarray(np.asarray(mask_img))
        else:
            mask_a = np.ascontiguousarray(mask)
        h, w = mask_a.shape
        rgba = np.empty((h, w, 4), dtype=np.uint8)
        rgba[:, :, 0] = rgb[0]
        rgba[:, :, 1] = rgb[1]
        rgba[:, :, 2] = rgb[2]
        rgba[:, :, 3] = (
            mask_a.astype(np.float32) * (max_alpha / 255.0)
        ).astype(np.uint8)
        rgba = np.ascontiguousarray(rgba)
        qimg = QImage(
            rgba.data, w, h, rgba.strides[0], QImage.Format.Format_RGBA8888
        )
        painter.drawImage(0, 0, qimg.copy())

    def _path_display_points(
        self, base_w: int, base_h: int
    ) -> list[QPoint]:
        if self._rgba is None or not self._sel_points:
            return []
        iw, ih = self._rgba.size
        sx = base_w / max(1, iw)
        sy = base_h / max(1, ih)
        pts = list(self._sel_points)
        # Rect preview as 4 corners while dragging
        if self._tool == RetouchTool.RECT and len(pts) >= 2:
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [QPoint(int(x * sx), int(y * sy)) for x, y in pts]

    def _refresh_display(self, immediate: bool = False):
        """Rebuild the viewport pixmap. Coalesced while painting/selecting.

        Working pixels stay full-resolution; this only updates what you see.
        """
        if immediate or not (self._painting or self._selecting):
            self._refresh_timer.stop()
            self._refresh_pending = False
            self._do_refresh_display()
            return
        self._refresh_pending = True
        ms = max(0, int(getattr(config, "retouchPaintRefreshMs", 16)))
        if ms <= 0:
            self._do_refresh_display()
            self._refresh_pending = False
            return
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(ms)

    def _flush_refresh(self):
        if self._refresh_pending:
            self._refresh_pending = False
            self._do_refresh_display()

    def _preview_rgba(self) -> Image.Image | None:
        """Current pixels for checkerboard (stroke buffer preferred)."""
        if self._rgba_arr is not None:
            return Image.fromarray(self._rgba_arr, "RGBA")
        return self._rgba

    def _do_refresh_display(self):
        src = self._preview_rgba()
        if src is None:
            return
        if self._base_checker is None:
            # 0 = original size - canvas buffer matches uploaded image WxH
            self._base_checker = checkerboard_pixmap_from_rgba(
                src, max_side=config.retouchPreviewMaxSide
            )

        base = self._base_checker
        fill_mask = self.get_fill_mask()
        protect_mask = self.get_protect_mask()
        need_paint = (
            (fill_mask is not None and np.any(fill_mask))
            or (protect_mask is not None and np.any(protect_mask))
            or self.has_selection()
            or bool(self._sel_points)
        )
        if need_paint:
            out = base.copy()
            painter = QPainter(out)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            if fill_mask is not None and np.any(fill_mask):
                self._draw_overlay_mask(
                    painter,
                    fill_mask,
                    base.width(),
                    base.height(),
                    (255, 48, 48),
                    config.retouchMaskOverlayAlpha,
                )

            if protect_mask is not None and np.any(protect_mask):
                self._draw_overlay_mask(
                    painter,
                    protect_mask,
                    base.width(),
                    base.height(),
                    (42, 210, 120),
                    config.retouchMaskOverlayAlpha,
                )

            if self.has_selection() and self._selection is not None:
                self._draw_overlay_mask(
                    painter,
                    self._selection,
                    base.width(),
                    base.height(),
                    SELECTION_PRIMARY,
                    config.retouchSelectionOverlayAlpha,
                )

            # In-progress path outline
            dpts = self._path_display_points(base.width(), base.height())
            if len(dpts) >= 1:
                pen = QPen(PATH_COLOR)
                pen.setWidth(2)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if len(dpts) == 1:
                    painter.drawEllipse(dpts[0], 3, 3)
                else:
                    for i in range(len(dpts) - 1):
                        painter.drawLine(dpts[i], dpts[i + 1])
                    if self._tool in (RetouchTool.LASSO, RetouchTool.RECT) and self._selecting:
                        painter.drawLine(dpts[-1], dpts[0])
                    if self._tool == RetouchTool.PEN and len(dpts) >= 3:
                        painter.drawEllipse(dpts[0], 5, 5)

            painter.end()
            self._display = out
        else:
            self._display = base
        self._render()

    def _handle_wheel(self, event: QWheelEvent):
        if self._display is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = config.zoomStep if delta > 0 else (1.0 / config.zoomStep)
        vp_pos = self.scroll.viewport().mapFromGlobal(event.globalPosition().toPoint())
        self._zoom_toward(factor, vp_pos)

    def zoom_in(self):
        self._zoom_toward(config.zoomStep, self.scroll.viewport().rect().center())

    def zoom_out(self):
        self._zoom_toward(1.0 / config.zoomStep, self.scroll.viewport().rect().center())

    def zoom_fit(self):
        self._fit_mode = True
        self._render()
        self._update_cursor()

    def zoom_actual(self):
        if self._rgba is None or self._display is None:
            self._set_zoom(1.0)
            return
        old = self._current_display_zoom()
        target = self._rgba.size[0] / max(1, self._display.width())
        if old <= 0:
            return
        self._zoom_toward(
            target / old, self.scroll.viewport().rect().center()
        )

    def _zoom_toward(self, factor: float, viewport_pos: QPoint):
        if self._display is None:
            return
        old_zoom = self._current_display_zoom()
        new_zoom = max(config.minZoom, min(config.maxZoom, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-6:
            return

        label_pos = self.image_label.mapFrom(self.scroll.viewport(), viewport_pos)
        old_w = max(1, self.image_label.width())
        old_h = max(1, self.image_label.height())
        rx = max(0.0, min(1.0, label_pos.x() / old_w))
        ry = max(0.0, min(1.0, label_pos.y() / old_h))

        self._fit_mode = False
        self._zoom = new_zoom
        self._render()
        self._update_cursor()

        new_w = max(1, self.image_label.width())
        new_h = max(1, self.image_label.height())
        self.scroll.horizontalScrollBar().setValue(int(rx * new_w - viewport_pos.x()))
        self.scroll.verticalScrollBar().setValue(int(ry * new_h - viewport_pos.y()))

    def _current_display_zoom(self) -> float:
        if self._fit_mode and self._display is not None:
            return self._fit_scale()
        return self._zoom

    def _fit_scale(self) -> float:
        if self._display is None:
            return 1.0
        vp = self.scroll.viewport().size()
        if vp.width() <= 1 or vp.height() <= 1:
            return 1.0
        sw, sh = self._display.width(), self._display.height()
        sx = (vp.width() - 4) / max(1, sw)
        sy = (vp.height() - 4) / max(1, sh)
        return max(config.minZoom, min(sx, sy, config.maxZoom))

    def _set_zoom(self, zoom: float):
        self._fit_mode = False
        self._zoom = max(config.minZoom, min(config.maxZoom, zoom))
        self._render()
        self._update_cursor()

    def _render(self):
        if self._display is None:
            return
        scale = self._fit_scale() if self._fit_mode else self._zoom
        if self._fit_mode:
            self._zoom = scale
        w = max(1, int(self._display.width() * scale))
        h = max(1, int(self._display.height() * scale))
        fast = self._painting or self._selecting
        scaled = self._display.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
            if fast
            else Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        if self._rgba is not None and self._rgba.size[0]:
            pct = int(round((scaled.width() / self._rgba.size[0]) * 100))
        else:
            pct = int(round(scale * 100))
        self.zoom_chrome.set_zoom_text(f"{'Fit ' if self._fit_mode else ''}{pct}%")

    def _screen_brush_diameter(self) -> int:
        if self._rgba is None:
            return max(4, self._radius * 2)
        pm = self._shown_pixmap()
        if pm is None or pm.isNull() or self._rgba.size[0] <= 0:
            return max(4, self._radius * 2)
        px_per_img = pm.width() / self._rgba.size[0]
        return max(4, int(round(2 * self._radius * px_per_img)))

    def _brush_cursor(self) -> QCursor:
        d = self._screen_brush_diameter()
        if d % 2 == 0:
            d += 1
        d = min(d, 255)
        key = ("brush", d)
        if self._cursor_cache_key == key and self._cursor_cache is not None:
            return self._cursor_cache
        pad = 2
        size = d + pad * 2
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen_outer = QPen(QColor(0, 0, 0, 220))
        pen_outer.setWidth(2)
        painter.setPen(pen_outer)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(pad, pad, d, d)
        pen_inner = QPen(QColor(255, 255, 255, 230))
        pen_inner.setWidth(1)
        painter.setPen(pen_inner)
        painter.drawEllipse(pad + 1, pad + 1, max(1, d - 2), max(1, d - 2))
        painter.end()
        hot = size // 2
        cur = QCursor(pm, hot, hot)
        self._cursor_cache_key = key
        self._cursor_cache = cur
        return cur

    @staticmethod
    def _tool_cursor_pen() -> QCursor:
        """Pencil tip - hotspot at the writing point."""
        size = 28
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(*_PRIMARY_RGB)
        outline = QColor(255, 255, 255, 230)
        body = [
            QPoint(8, 2),
            QPoint(11, 1),
            QPoint(24, 14),
            QPoint(21, 17),
        ]
        p.setPen(QPen(outline, 2.5))
        p.setBrush(color)
        p.drawPolygon(QPolygon(body))
        tip = [QPoint(2, 2), QPoint(8, 2), QPoint(5, 8)]
        p.setBrush(QColor(40, 40, 40))
        p.drawPolygon(QPolygon(tip))
        p.setPen(QPen(outline, 1.5))
        p.drawLine(9, 5, 12, 8)
        p.end()
        return QCursor(pm, 2, 2)

    @staticmethod
    def _tool_cursor_lasso() -> QCursor:
        """Lasso loop with handle - hotspot at tip of handle."""
        size = 28
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(*_PRIMARY_RGB)
        outline = QColor(255, 255, 255, 220)
        p.setPen(QPen(outline, 3.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(6, 2, 16, 14)
        p.setPen(QPen(color, 2.0))
        p.drawEllipse(6, 2, 16, 14)
        p.setPen(QPen(outline, 3.5))
        p.drawLine(10, 14, 3, 24)
        p.setPen(QPen(color, 2.0))
        p.drawLine(10, 14, 3, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(1, 22, 4, 4)
        p.end()
        return QCursor(pm, 3, 24)

    @staticmethod
    def _tool_cursor_rect() -> QCursor:
        """Crosshair with small rectangle - hotspot at center."""
        size = 25
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(*_PRIMARY_RGB)
        outline = QColor(255, 255, 255, 230)
        c = size // 2
        p.setPen(QPen(outline, 3))
        p.drawLine(c, 1, c, c - 4)
        p.drawLine(c, c + 4, c, size - 2)
        p.drawLine(1, c, c - 4, c)
        p.drawLine(c + 4, c, size - 2, c)
        p.setPen(QPen(color, 1.5))
        p.drawLine(c, 1, c, c - 4)
        p.drawLine(c, c + 4, c, size - 2)
        p.drawLine(1, c, c - 4, c)
        p.drawLine(c + 4, c, size - 2, c)
        p.setPen(QPen(outline, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(c - 5, c - 5, 10, 10)
        p.setPen(QPen(color, 1.2))
        p.drawRect(c - 5, c - 5, 10, 10)
        p.end()
        return QCursor(pm, c, c)

    def _select_tool_cursor(self) -> QCursor:
        key = ("select", self._tool)
        if self._cursor_cache_key == key and self._cursor_cache is not None:
            return self._cursor_cache
        if self._tool == RetouchTool.PEN:
            cur = self._tool_cursor_pen()
        elif self._tool == RetouchTool.LASSO:
            cur = self._tool_cursor_lasso()
        elif self._tool == RetouchTool.RECT:
            cur = self._tool_cursor_rect()
        else:
            cur = QCursor(Qt.CursorShape.CrossCursor)
        self._cursor_cache_key = key
        self._cursor_cache = cur
        return cur

    def _update_cursor(self):
        if not self._interaction_enabled and not self._want_pan():
            cur = QCursor(Qt.CursorShape.WaitCursor)
            self._cursor_cache_key = None
        elif self._want_pan():
            cur = QCursor(Qt.CursorShape.OpenHandCursor)
            self._cursor_cache_key = None
        elif self.is_select_tool():
            if self._tool == RetouchTool.SELECT_OBJECT:
                cur = QCursor(Qt.CursorShape.CrossCursor)
            else:
                cur = self._select_tool_cursor()
        else:
            cur = self._brush_cursor()
        self.image_label.setCursor(cur)
        self.scroll.viewport().setCursor(cur)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self._display is not None:
            self._render()
            self._update_cursor()
