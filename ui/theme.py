"""App theme — Midgard tokens (colors + sizes) and QSS builders.

Layout (FluentWindow):
  Title bar — top header chrome
  Nav rail  — left sidebar
  Content   — stacked pages (middle area + workspace rails)

Edit tokens here. Shell colors are applied once via ``apply_window_theme`` (called from ``ui.shell``).
Components read PAGE / NAV / HOME / WORKSPACE / SETTINGS / FORM / CARD / SECTION / PREVIEW / BUTTON instead of hardcoding values.
"""

from __future__ import annotations

# --- Colors ---
PRIMARY = "#7C3AED"
PRIMARY_HOVER = "#6D28D9"
PRIMARY_SOFT = "#2A2240"
WHITE_COLOR = "#FFFFFF"

BG = "#0F1113"
BORDER = "#2A2D31"
TEXT = WHITE_COLOR
TEXT_SECONDARY = "#898A8B"

DARK_BG = BG

ERROR = "#EF4444"
WARNING = "#F59E0B"
WARNING_HOVER = "#D97706"
SUCCESS = "#1BD12A"
INFO = TEXT
MUTED = "#16181B"
BORDER_STRONG = "#1F2937"
PROCESSING = "#38BDF8"
DANGER_HOVER = "#B91C1C"

STATUS = {
    "error": ERROR,
    "warning": WARNING,
    "success": SUCCESS,
    "info": INFO,
    "processing": PROCESSING,
    "muted": TEXT_SECONDARY,
}

CARD_RADIUS = 6

# --- Page shell (content stack background + generic gutters) ---
PAGE = {
    "bg": BG,
    "margin": 12,
    "spacing": 12,
    "column_spacing": 10,
}

# --- Home dashboard ---
HOME = {
    "pad_x": 200,
    "pad_top": 20,
    "pad_bottom": 20,
    "gap": 8,
    "sub_gap": 6,
    "after_greet": 4,
    "section_gap": 28,
    "section_title_gap": 10,
    "prompt_gap": 24,
    "hint_gap": 8,
    "prompt_h": 90,
}

# --- Tool workspace (preview + log + task rail) ---
WORKSPACE = {
    "rail_width": 300,
    "rail_spacing": 10,
    "log_min_h": 72,
    "log_max_h": 100,
    "action_bar_min_h": 100,
    "preview_stretch": 5,
    "log_stretch": 0,
    "task_stretch": 1,
}

# --- Settings pages / setting cards ---
SETTINGS = {
    "spacing": 12,
    "margin": 12,
    "bottom": 40,
    "group_title_size": 12,
    "group_title_weight": 600,
    "group_spacing": 8,
    "card_stack_spacing": 4,
    "content_ratio": 0.8,
    "content_min_w": 360,
    "risk_badge_size": 8,
    "risk_badge_pad_x": 6,
    "risk_badge_radius": 4,
    "card_height": 72,
    "card_content_max_h": 22,
    "section_desc_size": 11,
}

# --- Form fields (inputs, combos, tight rows) ---
FORM = {
    "field_spacing": 12,
    "combo_max_visible": 12,
    "tight_spacing": 4,
}

# --- Side nav (Fluent NavigationInterface) ---
NAV = {
    "bg": BG,
    "border": BORDER,
    "expand_w": 200,
    "brand_h": 40,
    "brand_logo": 18,
    "brand_title_size": 13,
    "brand_pad_x": 12,
    "brand_gap": 8,
    "top_pad_y": 20,
    "top_pad_x": 16,
    "top_spacing": 4,
    "item_h": 36,
    "meter_font": 10,
    "meter_pad_x": 12,
    "meter_pad_y": 6,
    "meter_gap": 2,
    "meter_interval_ms": 2000,
}

# --- Video preview controls ---
VIDEO = {
    "slider_h": 22,
    "control_pad": 12,
    "control_spacing": 10,
    "control_radius": 16,
    "control_bg": "#000000",
}

# --- Dialogs (Retouch / Enhance / Confirm) ---
DIALOG = {
    "pad": 18,
    "spacing": 16,
    "rail_spacing": 16,
    "combo_min_w": 220,
    "tool_gap": 5,
    "progress_spacing": 6,
    "confirm_w": 340,
    "confirm_wrap_min": 28,
    "confirm_wrap_max": 48,
    "confirm_wrap_div": 7,
    "confirm_extra_h": 105,
}

# --- Row cards (Home / Settings lists) ---
CARD = {
    "height": 68,
    "radius": CARD_RADIUS,
    "bg": MUTED,
    "border": BORDER,
    "title": TEXT,
    "content": TEXT_SECONDARY,
    "pad_x_left": 12,
    "pad_x_right": 10,
    "pad_y": 6,
    "icon": 14,
    "icon_gap": 12,
    "title_size": 9,
    "content_size": 8,
    "content_max_h": 36,
    "spacing": 2,
    "slider_min_w": 200,
    "control_gap": 8,
    "value_gap": 6,
    "trailing_gap": 16,
}
COMPACT_HEIGHT = CARD["height"]

# --- Range sliders (settings cards, retouch controls) ---
SLIDER = {

    "handle": 18,
    "groove_h": 4,
    "track": BORDER,
    "fill": TEXT_SECONDARY,
    "handle_color": PRIMARY,
}

# --- Section panes (Preview / Settings / Tasks / Log) ---
SECTION = {
    "bg": MUTED,
    "border": BORDER,
    "title": TEXT,
    "title_size": 10,
    "radius": CARD_RADIUS,
    "pad": 14,
    "spacing": 10,
}

# --- Before / After / drag-drop zoom panes ---
PREVIEW = {
    "bg": BG,
    "border": BORDER,
    "border_active": PRIMARY,
    "radius": CARD_RADIUS,
    "title": TEXT,
    "title_size": 15,
    "title_weight": 600,
    "content": TEXT_SECONDARY,
    "content_size": 12,
    "link": PRIMARY,
    "link_weight": 700,
    "badge_bg": MUTED,
    "badge_border": BORDER,
    "badge_icon": TEXT_SECONDARY,
    "badge_size": 56,
    "upload_icon": 28,
    "border_width": 1,
    "border_width_active": 2,
    "border_width_dash": 1.5,
    "dash": (4, 3),
    "pad": 14,
    "upload_pad": 28,
    "spacing": 10,
    "zoom_gap": 8,
    "zoom_label_min_w": 64,
    "min_h": 240,
    "selection_active": PRIMARY,
    "selection_idle": WARNING,
    "checker_a": (220, 220, 220, 255),
    "checker_b": (180, 180, 180, 255),
}


def card_qss() -> str:
    c = CARD
    return f"""
        MidgardSettingCard, QFrame#MidgardSettingCard, QFrame#InfoSettingCard {{
            background-color: {c["bg"]};
            border: 1px solid {c["border"]};
            border-radius: {c["radius"]}px;
        }}
        MidgardSettingCard QLabel, QFrame#MidgardSettingCard QLabel, QFrame#InfoSettingCard QLabel {{
            background: transparent;
            border: none;
        }}
        MidgardSettingCard QLabel#titleLabel, QFrame#InfoSettingCard QLabel#titleLabel {{
            color: {c["title"]};
        }}
        MidgardSettingCard QLabel#contentLabel, QFrame#InfoSettingCard QLabel#contentLabel {{
            color: {c["content"]};
        }}
    """


def _paint_widget_bg(widget, color: str, *, extra: str = "") -> None:
    """Set background on one widget (selector scoped so children keep their own bg)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractScrollArea

    if widget is None:
        return
    name = widget.objectName()
    cls = widget.metaObject().className()
    if name:
        rule = f"{cls}#{name}"
    else:
        rule = cls
    qss = f"{rule} {{ background-color: {color}; border: none;{extra} }}"
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)
    widget.setStyleSheet(qss)
    if isinstance(widget, QAbstractScrollArea):
        vp = widget.viewport()
        if not vp.objectName():
            base = widget.objectName() or "ScrollArea"
            vp.setObjectName(f"{base}Viewport")
        _paint_widget_bg(vp, color, extra=extra)


def apply_page_bg(*widgets) -> None:
    """Home scroll areas — Qt viewports default to white."""
    for w in widgets:
        _paint_widget_bg(w, PAGE["bg"])


def _nav_border_extra() -> str:
    return f" border-right: 1px solid {NAV['border']};"


def _paint_nav(nav) -> None:
    from PySide6.QtWidgets import QWidget

    if nav is None:
        return
    border = _nav_border_extra()
    _paint_widget_bg(nav, NAV["bg"], extra=border)
    panel = getattr(nav, "panel", None)
    if panel is not None:
        _paint_widget_bg(panel, NAV["bg"], extra=border)
    if panel is None:
        return
    brand = panel.findChild(QWidget, "NavBrand")
    if brand is not None:
        _paint_widget_bg(brand, NAV["bg"])
    for part in (
        getattr(panel, "scrollArea", None),
        getattr(panel, "scrollWidget", None),
        getattr(panel, "view", None),
    ):
        if isinstance(part, QWidget):
            _paint_widget_bg(part, NAV["bg"])


def apply_window_theme(window) -> None:
    """Called once from ``ui.shell.apply_shell`` — header, nav, page stack."""
    from PySide6.QtCore import Qt
    from qfluentwidgets import setCustomStyleSheet

    if hasattr(window, "setCustomBackgroundColor"):
        window.setCustomBackgroundColor(BG, BG)

    title = getattr(window, "titleBar", None)
    if title is not None:
        _paint_widget_bg(title, BG)
        qss = title.styleSheet()
        setCustomStyleSheet(title, qss, qss)

    _paint_nav(getattr(window, "navigationInterface", None))

    stacked = getattr(window, "stackedWidget", None)
    if stacked is not None:
        stacked.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        stacked.setAutoFillBackground(True)
        stacked.setStyleSheet(
            f"StackedWidget, PopUpAniStackedWidget {{"
            f" background-color: {PAGE['bg']}; border: none; }}"
        )

    dash = getattr(window, "dashboardInterface", None)
    if dash is not None and hasattr(dash, "apply_theme_bg"):
        dash.apply_theme_bg()


# --- Buttons ---
BUTTON_RADIUS = 6
BUTTON = {
    "primary": {
        "bg": PRIMARY,
        "bg_hover": PRIMARY_HOVER,
        "bg_pressed": PRIMARY_HOVER,
        "fg": WHITE_COLOR,
        "border": "transparent",
    },
    "danger": {
        "bg": ERROR,
        "bg_hover": DANGER_HOVER,
        "bg_pressed": DANGER_HOVER,
        "fg": WHITE_COLOR,
        "border": "transparent",
    },
    "warning": {
        "bg": WARNING,
        "bg_hover": WARNING_HOVER,
        "bg_pressed": WARNING_HOVER,
        "fg": "#000000",
        "border": "transparent",
    },
    "secondary": {
        "bg": MUTED,
        "bg_hover": BORDER,
        "bg_pressed": BORDER,
        "fg": TEXT,
        "fg_hover": WHITE_COLOR,
        "border": BORDER,
        "border_hover": BORDER_STRONG,
        # Checkable toggles (Automatic / Protect, tool peers): solid primary when on
        "checked_bg": PRIMARY,
        "checked_fg": WHITE_COLOR,
        "checked_border": PRIMARY,
        "checked_bg_hover": PRIMARY_HOVER,
        "checked_fg_hover": WHITE_COLOR,
        "checked_border_hover": PRIMARY_HOVER,
    },
    "disabled": {
        "bg": MUTED,
        "fg": TEXT_SECONDARY,
        "border": BORDER,
    },
}

BUTTON_SIZE_SMALL = "small"
BUTTON_SIZE_MEDIUM = "medium"
BUTTON_SIZE_LARGE = "large"

BUTTON_SIZES = {
    BUTTON_SIZE_SMALL: {"height": 24, "pad_x": 8, "pad_y": 2, "font": 11, "icon": 12},
    BUTTON_SIZE_MEDIUM: {"height": 32, "pad_x": 12, "pad_y": 6, "font": 12, "icon": 14},
    BUTTON_SIZE_LARGE: {"height": 40, "pad_x": 16, "pad_y": 8, "font": 14, "icon": 16},
}


def button_qss(role: str = "primary") -> str:
    p = BUTTON[role]
    d = BUTTON["disabled"]
    sel = "PrimaryPushButton" if role == "primary" else "PushButton"
    border = p.get("border") or p["bg"]
    border_hover = p.get("border_hover") or p.get("bg_hover") or border
    fg_hover = p.get("fg_hover") or p["fg"]
    qss = f"""
        {sel} {{
            color: {p["fg"]} !important;
            background-color: {p["bg"]} !important;
            border: 1px solid {border} !important;
            border-radius: {BUTTON_RADIUS}px;
            padding: 5px 12px 6px 12px;
        }}
        {sel}:hover {{
            color: {fg_hover} !important;
            background-color: {p["bg_hover"]} !important;
            border: 1px solid {border_hover} !important;
        }}
        {sel}:pressed {{
            color: {p["fg"]} !important;
            background-color: {p["bg_pressed"]} !important;
            border: 1px solid {p["bg_pressed"]} !important;
            border-bottom: 1px solid {p["bg_pressed"]} !important;
        }}
        {sel}:disabled {{
            color: {d["fg"]} !important;
            background-color: {d["bg"]} !important;
            border: 1px solid {d.get("border", d["bg"])} !important;
        }}
    """
    checked_bg = p.get("checked_bg")
    if checked_bg:
        checked_fg = p.get("checked_fg") or WHITE_COLOR
        checked_border = p.get("checked_border") or checked_bg
        checked_bg_hover = p.get("checked_bg_hover") or checked_bg
        checked_fg_hover = p.get("checked_fg_hover") or checked_fg
        checked_border_hover = p.get("checked_border_hover") or checked_border
        qss += f"""
        {sel}:checked {{
            color: {checked_fg} !important;
            background-color: {checked_bg} !important;
            border: 1px solid {checked_border} !important;
        }}
        {sel}:checked:hover {{
            color: {checked_fg_hover} !important;
            background-color: {checked_bg_hover} !important;
            border: 1px solid {checked_border_hover} !important;
        }}
        {sel}:checked:pressed {{
            color: {checked_fg} !important;
            background-color: {checked_bg_hover} !important;
            border: 1px solid {checked_bg_hover} !important;
        }}
        {sel}:checked:disabled {{
            color: {d["fg"]} !important;
            background-color: {d["bg"]} !important;
            border: 1px solid {d.get("border", d["bg"])} !important;
        }}
        """
    return qss
