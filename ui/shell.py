"""App shell — full-height sidebar (brand + nav) + content header.

  ┌─────────────┬─────────────────────────────────┐
  │ logo + name │  title bar (window controls)    │
  │─────────────│                                 │
  │ nav routes  │  stacked pages                  │
  │             │                                 │
  └─────────────┴─────────────────────────────────┘
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWidgets import QStackedWidget, QWidget
from qfluentwidgets import FluentIcon, NavigationItemPosition, TitleLabel

from ui.theme import NAV, TEXT, apply_window_theme

HEADER_H = 48
APP_ICON = "ui/icon/icon_48.png"


class ContentPage(QWidget):
    """One routed page — no extra chrome; tools/widgets go in ``body``."""

    def __init__(self, object_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.body = QtWidgets.QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)


@dataclass(frozen=True)
class NavRoute:
    page: QWidget
    icon: Union[FluentIcon, object]
    label: str
    position: NavigationItemPosition = NavigationItemPosition.TOP


def _nav_width(window) -> int:
    nav = getattr(window, "navigationInterface", None)
    if nav is None or not nav.isVisible():
        return 0
    return nav.width()


def configure_header(window) -> None:
    """Content-area title bar only — logo/title live in the sidebar."""
    window.hBoxLayout.setContentsMargins(0, 0, 0, 0)
    window.widgetLayout.setContentsMargins(0, HEADER_H, 0, 0)

    bar = window.titleBar
    bar.iconLabel.hide()
    bar.titleLabel.hide()
    sync_header_geometry(window)
    bar.raise_()


def sync_header_geometry(window) -> None:
    nav_w = _nav_width(window)
    bar = window.titleBar
    bar.move(nav_w, 0)
    bar.resize(max(window.width() - nav_w, 1), HEADER_H)
    bar.raise_()


def _add_nav_brand(panel, *, title: str, icon_path: str) -> QWidget:
    brand = QtWidgets.QWidget(panel)
    brand.setObjectName("NavBrand")
    brand.setFixedHeight(NAV["brand_h"])

    row = QtWidgets.QHBoxLayout(brand)
    row.setContentsMargins(NAV["brand_pad_x"], 0, NAV["brand_pad_x"], 0)
    row.setSpacing(NAV["brand_gap"])

    logo = QtWidgets.QLabel(brand)
    side = NAV["brand_logo"]
    logo.setFixedSize(side, side)
    logo.setPixmap(QtGui.QIcon(icon_path).pixmap(side, side))
    logo.setScaledContents(True)

    name = TitleLabel(title, brand)
    name.setStyleSheet(
        f"color: {TEXT}; background: transparent; font-size: {NAV['brand_title_size']}px;"
    )

    row.addWidget(logo, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(name, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    row.addStretch(1)

    panel.vBoxLayout.insertWidget(0, brand)
    return brand


def _apply_nav_layout(panel) -> None:
    """Apply ``NAV`` padding/spacing to Fluent ``NavigationPanel`` layouts."""
    px = NAV["top_pad_x"]
    py = NAV["top_pad_y"]
    panel.topLayout.setContentsMargins(px, py, px, 0)
    panel.topLayout.setSpacing(NAV["top_spacing"])
    margins = panel.vBoxLayout.getContentsMargins()
    panel.vBoxLayout.setContentsMargins(margins[0], 0, margins[2], margins[3])


def _apply_nav_item_height(panel) -> None:
    from qfluentwidgets.components.navigation.navigation_widget import NavigationWidget

    item_h = NAV["item_h"]
    compact_w = 40
    for widget in panel.findChildren(NavigationWidget):
        width = compact_w if widget.isCompacted else NavigationWidget.EXPAND_WIDTH
        widget.setFixedSize(width, item_h)


def _add_nav_resource_meter(window, panel) -> None:
    """Settings stays last among nav items; meter sits inline below it."""
    from qfluentwidgets.components.navigation.navigation_panel import NavigationDisplayMode

    from ui.component.nav_resource_meter import NavResourceMeter

    # Ensure Settings (BOTTOM nav item) is above the meter: insert meter at end.
    # Fluent stacks bottom items with AlignBottom; put meter after all nav widgets.
    meter = getattr(window, "navResourceMeter", None)
    if meter is None:
        meter = NavResourceMeter(panel)
        window.navResourceMeter = meter
    else:
        panel.bottomLayout.removeWidget(meter)

    panel.bottomLayout.addWidget(meter, 0, QtCore.Qt.AlignmentFlag.AlignBottom)

    def _sync_compact(mode=None):
        if mode is None:
            mode = panel.displayMode
        meter.set_compact(mode != NavigationDisplayMode.EXPAND)

    _sync_compact()
    if not getattr(window, "_nav_meter_hooked", False):
        nav = window.navigationInterface
        nav.displayModeChanged.connect(_sync_compact)
        window._nav_meter_hooked = True


def setup_nav(
    window,
    *,
    title: str,
    icon_path: str = APP_ICON,
    expand_w: int | None = None,
    collapsible: bool = True,
    return_visible: bool = False,
) -> None:
    nav = window.navigationInterface
    panel = nav.panel
    nav.setReturnButtonVisible(return_visible)
    nav.setExpandWidth(expand_w if expand_w is not None else NAV["expand_w"])
    nav.setCollapsible(collapsible)
    nav.setMenuButtonVisible(bool(collapsible))
    _add_nav_brand(panel, title=title, icon_path=icon_path)
    _apply_nav_layout(panel)
    try:
        nav.expand(useAni=False)
    except TypeError:
        nav.expand()
    except Exception:
        pass
    # After routes + expand so Settings is already in bottomLayout, then meter after it.
    _add_nav_resource_meter(window, panel)
    _apply_nav_item_height(panel)
    if not getattr(window, "_nav_geometry_hooked", False):
        nav.displayModeChanged.connect(lambda _mode: sync_header_geometry(window))
        window._nav_geometry_hooked = True
    sync_header_geometry(window)


def register_routes(window, routes: list[NavRoute]) -> None:
    """Wire nav items → stacked pages (FluentWindow routing)."""
    for route in routes:
        window.addSubInterface(
            route.page,
            route.icon,
            route.label,
            route.position,
        )


def enable_instant_page_switch(window) -> None:
    """Skip PopUpAniStackedWidget animation (flickers on Linux/Wayland)."""

    def _instant(widget, popOut=True):
        from PySide6.QtWidgets import QAbstractScrollArea

        if isinstance(widget, QAbstractScrollArea):
            widget.verticalScrollBar().setValue(0)
        view = window.stackedWidget.view
        if view.currentWidget() is widget:
            return
        ani = getattr(view, "_ani", None)
        if ani is not None and ani.state() == QtCore.QAbstractAnimation.Running:
            ani.stop()
        QStackedWidget.setCurrentWidget(view, widget)

    window.stackedWidget.setCurrentWidget = _instant


def apply_shell(window) -> None:
    """Paint nav + content stack after pages are registered."""
    apply_window_theme(window)
