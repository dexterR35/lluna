# -*- coding: utf-8 -*-
"""Install Qt-side diagnostic hooks (nav, optional clicks, model config).

By default this does **not** log every button click (zoom, chrome, etc.).
Pipeline / process logs come from UPLOAD RUN MODEL WORKER PROCESS PROGRESS.

Opt-in noisy UI clicks:
  MIDGARD_DIAG_CLICKS=1 ./run_gui.sh
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from backend.tools import diag


def _widget_label(w: QWidget) -> str:
    name = w.objectName() or ""
    text = ""
    if hasattr(w, "text"):
        try:
            text = str(w.text() or "").strip()
        except Exception:
            text = ""
    if not text and hasattr(w, "toolTip"):
        try:
            text = str(w.toolTip() or "").strip()
        except Exception:
            text = ""
    cls = type(w).__name__
    bits = [cls]
    if name:
        bits.append(f"#{name}")
    if text:
        short = text.replace("\n", " ")
        if len(short) > 48:
            short = short[:45] + "…"
        bits.append(f'"{short}"')
    return " ".join(bits)


def _page_name(widget: Optional[QWidget]) -> str:
    if widget is None:
        return "<none>"
    name = widget.objectName() or type(widget).__name__
    return name


def _mode_key(value: Any) -> str:
    if value is None:
        return "<none>"
    if hasattr(value, "name"):
        return str(value.name)
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        try:
            return str(value.value)
        except Exception:
            pass
    return str(value)


def _mode_label(section: str, value: Any) -> str:
    try:
        from backend.config import tr

        name = getattr(value, "name", None)
        if name and section in tr:
            return str(tr[section].get(name, name))
    except Exception:
        pass
    return _mode_key(value)


def _clicks_enabled() -> bool:
    """Noisy Qt button-click logging — off unless MIDGARD_DIAG_CLICKS=1."""
    import os

    raw = os.environ.get("MIDGARD_DIAG_CLICKS", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class DiagEventFilter(QObject):
    """Optional app-wide button click logger (zoom/chrome spam — opt-in only)."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if not diag.is_enabled() or not _clicks_enabled():
            return False
        et = event.type()
        try:
            if et == QEvent.Type.MouseButtonRelease and isinstance(obj, QAbstractButton):
                cls = type(obj).__name__
                if "Combo" in cls or hasattr(obj, "currentIndexChanged"):
                    return False
                # Skip zoom / tool chrome — almost never useful in pipeline debugging
                if cls in ("ToolButton", "TransparentToolButton", "NavigationToolButton"):
                    return False
                tip = ""
                try:
                    tip = str(obj.toolTip() or "").lower()
                except Exception:
                    tip = ""
                if any(k in tip for k in ("zoom", "actual size", "fit", "wheel")):
                    return False
                if obj.isEnabled() and obj.isVisible():
                    btn = event.button() if hasattr(event, "button") else None
                    if btn in (None, Qt.MouseButton.LeftButton):
                        diag.button(f"click  {_widget_label(obj)}")
        except Exception:
            pass
        return False


_filter: Optional[DiagEventFilter] = None
_config_hooks_installed = False


def install_app_hooks(app: QApplication) -> None:
    global _filter
    if not diag.is_enabled():
        return
    if _clicks_enabled():
        if _filter is None:
            _filter = DiagEventFilter(app)
            app.installEventFilter(_filter)
            diag.start("app click filter ON (MIDGARD_DIAG_CLICKS=1)")
    else:
        diag.start(
            "pipeline diag ON  (UPLOAD RUN MODEL WORKER PROCESS)  "
            "clicks off — set MIDGARD_DIAG_CLICKS=1 to enable"
        )


def install_config_hooks() -> None:
    """Log real model / mode changes (UI combo or programmatic config.set)."""
    global _config_hooks_installed
    if not diag.is_enabled() or _config_hooks_installed:
        return
    try:
        from qfluentwidgets import qconfig

        from backend.config import config
    except Exception as e:
        diag.warn(f"config hooks skipped: {e}")
        return

    watched = [
        ("inpaintMode", getattr(config, "inpaintMode", None), "InpaintMode"),
        ("subtitleDetectMode", getattr(config, "subtitleDetectMode", None), "SubtitleDetectMode"),
        ("bgRemoveMode", getattr(config, "bgRemoveMode", None), "BgRemoveMode"),
        ("enhanceMode", getattr(config, "enhanceMode", None), "EnhanceMode"),
    ]

    for key, item, section in watched:
        if item is None:
            continue
        try:
            initial = qconfig.get(item)
        except Exception:
            initial = getattr(item, "value", None)
        state = {"value": _mode_key(initial)}
        diag.model(f"{key}  initial={state['value']}  ({_mode_label(section, initial)})")

        def _on_changed(value, *, key=key, section=section, state=state):
            new_key = _mode_key(value)
            old_key = state["value"]
            if new_key == old_key:
                return
            label = _mode_label(section, value)
            diag.model(f"{key}  {old_key} → {new_key}  ({label})")
            state["value"] = new_key

        try:
            item.valueChanged.connect(_on_changed)
        except Exception as e:
            diag.warn(f"could not watch {key}: {e}")

    hw = getattr(config, "hardwareAcceleration", None)
    if hw is not None:
        try:
            hw_state = {"value": bool(qconfig.get(hw))}
            diag.model(f"hardwareAcceleration  initial={hw_state['value']}")

            def _on_hw(checked, state=hw_state):
                on = bool(checked)
                if on == state["value"]:
                    return
                diag.model(f"hardwareAcceleration  {state['value']} → {on}")
                state["value"] = on

            hw.valueChanged.connect(_on_hw)
        except Exception:
            pass

    _config_hooks_installed = True
    diag.start("config model hooks installed")


def install_window_hooks(window: Any) -> None:
    """Hook navigation / stacked page changes on the main window."""
    if not diag.is_enabled():
        return

    install_config_hooks()

    stacked = getattr(window, "stackedWidget", None)
    if stacked is not None:
        view = getattr(stacked, "view", stacked)

        def _on_page_changed(index: int) -> None:
            try:
                w = view.widget(index) if hasattr(view, "widget") else None
                diag.nav(f"page → {_page_name(w)}  (index={index})")
            except Exception as e:
                diag.warn(f"page change log failed: {e}")

        try:
            view.currentChanged.connect(_on_page_changed)
            cur = view.currentWidget() if hasattr(view, "currentWidget") else None
            diag.nav(f"initial page  {_page_name(cur)}")
        except Exception as e:
            diag.warn(f"could not hook stackedWidget: {e}")

    if hasattr(window, "switchTo") and not getattr(window, "_diag_switch_wrapped", False):
        original = window.switchTo

        def _switch(interface, *args, **kwargs):
            diag.nav(f"switchTo  {_page_name(interface)}")
            return original(interface, *args, **kwargs)

        window.switchTo = _switch
        window._diag_switch_wrapped = True
        diag.start("window nav hooks installed")
