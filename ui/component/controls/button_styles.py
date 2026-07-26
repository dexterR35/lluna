
from __future__ import annotations

import time
from typing import Literal, Optional, Union

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentIcon,
    FluentIconBase,
    PrimaryPushButton,
    PushButton,
    Theme,
    qconfig,
    setCustomStyleSheet,
    setThemeColor,
)

from ui.theme import (
    BUTTON,
    BUTTON_RADIUS,
    BUTTON_SIZE_MEDIUM,
    BUTTON_SIZES,
    PRIMARY,
    button_qss,
)

ButtonRole = Literal["primary", "secondary", "danger", "warning"]
ButtonSize = Literal["small", "medium", "large"]
FluentButton = Union[PushButton, PrimaryPushButton]

DEFAULT_CLICK_THROTTLE_MS = 450

_ACCENT_APPLIED: str | None = None


class ClickThrottle:
    """Ignore rapid repeat clicks without fighting external setEnabled()."""

    def __init__(self, interval_ms: int = DEFAULT_CLICK_THROTTLE_MS):
        self._interval = max(0, int(interval_ms)) / 1000.0
        self._last = 0.0

    def allow(self) -> bool:
        now = time.monotonic()
        if self._interval > 0 and (now - self._last) < self._interval:
            return False
        self._last = now
        return True

    def reset(self) -> None:
        self._last = 0.0


def _size_tokens(size: ButtonSize) -> dict:
    return BUTTON_SIZES.get(size, BUTTON_SIZES[BUTTON_SIZE_MEDIUM])


def ensure_theme_accent():
    """Point Fluent’s accent at theme PRIMARY - once per color (not every button)."""
    global _ACCENT_APPLIED
    if _ACCENT_APPLIED == PRIMARY:
        return
    setThemeColor(PRIMARY, save=False)
    _ACCENT_APPLIED = PRIMARY


def _apply_theme_chrome(btn: FluentButton, role: ButtonRole) -> None:
    """Paint button with ``theme.button_qss(role)`` - overrides Fluent defaults."""
    qss = button_qss(role)
    setCustomStyleSheet(btn, qss, qss)


def _primary_pushbutton_qss() -> str:
    """Primary fill using PushButton selector (for checkable secondary toggles)."""
    p = BUTTON["primary"]
    d = BUTTON["disabled"]
    border = p.get("border") or p["bg"]
    return f"""
        PushButton {{
            color: {p["fg"]} !important;
            background-color: {p["bg"]} !important;
            border: 1px solid {border} !important;
            border-radius: {BUTTON_RADIUS}px;
            padding: 5px 12px 6px 12px;
        }}
        PushButton:hover {{
            color: {p["fg"]} !important;
            background-color: {p["bg_hover"]} !important;
            border: 1px solid {p["bg_hover"]} !important;
        }}
        PushButton:pressed {{
            color: {p["fg"]} !important;
            background-color: {p["bg_pressed"]} !important;
            border: 1px solid {p["bg_pressed"]} !important;
        }}
        PushButton:disabled {{
            color: {d["fg"]} !important;
            background-color: {d["bg"]} !important;
            border: 1px solid {d.get("border", d["bg"])} !important;
        }}
    """


def paint_toggle_button(btn: FluentButton) -> None:
    """Checked → solid primary; unchecked → secondary. Call after setChecked."""
    ensure_theme_accent()
    if btn.isChecked():
        qss = _primary_pushbutton_qss()
        setCustomStyleSheet(btn, qss, qss)
    else:
        _apply_theme_chrome(btn, "secondary")


def style_as_toggle(btn: FluentButton) -> FluentButton:
    """Mark checkable and keep primary chrome in sync with checked state."""
    btn.setCheckable(True)
    btn.toggled.connect(lambda _=False, b=btn: paint_toggle_button(b))
    paint_toggle_button(btn)
    return btn


def _to_icon(icon, *, color: str | None = None) -> Optional[QIcon]:
    """Tint Fluent icons; default dark-theme glyphs when color is omitted."""
    if icon is None:
        return None
    if isinstance(icon, QIcon):
        return icon
    if isinstance(icon, FluentIconBase):
        if color is not None:
            return icon.icon(color=QColor(color))
        return icon.icon(Theme.DARK)
    return QIcon(icon) if icon else None


def make_button(
    text: str,
    role: ButtonRole,
    parent: QWidget | None = None,
    icon=None,
    size: ButtonSize = BUTTON_SIZE_MEDIUM,
) -> FluentButton:
    """Build a button styled entirely from ``ui.theme`` BUTTON tokens."""
    ensure_theme_accent()
    if size not in BUTTON_SIZES:
        size = BUTTON_SIZE_MEDIUM
    tokens = _size_tokens(size)

    if role == "primary":
        btn = PrimaryPushButton(text, parent)
    else:
        btn = PushButton(text, parent)

    _apply_theme_chrome(btn, role)

    icon_color = BUTTON.get(role, {}).get("fg") if role in ("primary", "danger", "warning") else None
    qicon = _to_icon(icon, color=icon_color)
    if qicon is not None:
        btn.setIcon(qicon)
    btn.setIconSize(QSize(tokens["icon"], tokens["icon"]))
    btn.setFixedHeight(tokens["height"])
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def make_toggle_button(
    text: str,
    parent: QWidget | None = None,
    icon=None,
    size: ButtonSize = BUTTON_SIZE_MEDIUM,
) -> FluentButton:
    """Secondary checkable button - primary fill while checked."""
    return style_as_toggle(make_button(text, "secondary", parent, icon=icon, size=size))


def make_stop_button(
    text: str,
    parent: QWidget | None = None,
    size: ButtonSize = BUTTON_SIZE_MEDIUM,
) -> FluentButton:
    return make_button(text, "danger", parent, icon=FluentIcon.CANCEL, size=size)


qconfig.themeChanged.connect(lambda *_: ensure_theme_accent())
