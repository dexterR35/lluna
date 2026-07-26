# -*- coding: utf-8 -*-
"""Midgard main window - header + nav shell, stacked tool pages."""

import sys
import multiprocessing

from backend.tools.diag import parse_cli_flags, banner
from backend.tools import diag

parse_cli_flags()

from backend.tools.paddle_cdn_patch import strip_paddle_cdn_hoster_check

strip_paddle_cdn_hoster_check()

from PySide6.QtCore import Qt
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QStackedWidget, QAbstractScrollArea

from backend.config import config, tr, VERSION
from qfluentwidgets import FluentWindow, FluentIcon, NavigationItemPosition, InfoBar

from backend.tools.process_manager import ProcessManager
from ui.advanced_setting_interface import AdvancedSettingInterface
from ui.dashboard_interface import DashboardInterface
from ui.home_interface import HomeInterface
from ui.bg_remove_interface import BgRemoveInterface
from ui.diag_hooks import install_app_hooks, install_window_hooks
from ui.shell import (
    APP_ICON,
    NavRoute,
    apply_shell,
    configure_header,
    enable_instant_page_switch,
    register_routes,
    setup_nav,
    sync_header_geometry,
)


class SubtitleExtractorGUI(FluentWindow):
    def __init__(self):
        super().__init__()
        diag.start("building main window")
        self.setMicaEffectEnabled(config.micaEnabled)
        self.setWindowIcon(QtGui.QIcon(APP_ICON))
        self.setWindowTitle(tr["SubtitleExtractorGUI"]["Title"] + " v" + VERSION)

        configure_header(self)
        self._pages = self._build_pages()
        register_routes(self, self._pages)
        setup_nav(
            self,
            title=tr["SubtitleExtractorGUI"]["Title"],
            collapsible=config.navCollapsible,
            return_visible=config.navReturnButtonVisible,
        )
        enable_instant_page_switch(self)
        self._wire_dashboard()
        self._wire_settings()
        apply_shell(self)

        config.appRestartSig.connect(self._show_restart_tooltip)
        self._schedule_update_check()
        try:
            from backend.tools.soft_defaults import apply_soft_defaults_if_needed

            apply_soft_defaults_if_needed()
        except Exception:
            pass
        try:
            from backend.tools.infer_client import InferClient

            InferClient.instance().ensure_started()
        except Exception as e:
            diag.error(f"infer worker failed to start  {e}")
        try:
            from backend.tools.diag_health import report_startup

            report_startup()
        except Exception as e:
            diag.warn(f"startup health check failed  {e}")
        diag.start("main window ready (pages + nav + infer worker)")

    def _build_pages(self) -> list[NavRoute]:
        self.dashboardInterface = DashboardInterface(self)
        self.dashboardInterface.setObjectName("DashboardInterface")
        self.bgRemoveInterface = BgRemoveInterface(self)
        self.homeInterface = HomeInterface(self)
        self.advancedSettingInterface = AdvancedSettingInterface(self)
        self.advancedSettingInterface.setObjectName("AdvancedSettingInterface")

        return [
            NavRoute(
                self.dashboardInterface,
                FluentIcon.HOME,
                tr["HomeDashboard"]["TabTitle"],
            ),
            NavRoute(
                self.bgRemoveInterface,
                FluentIcon.PHOTO,
                tr["BgRemove"]["Title"],
            ),
            NavRoute(
                self.homeInterface,
                FluentIcon.MOVIE,
                tr["SubtitleExtractorGUI"]["TabTitle"],
            ),
            NavRoute(
                self.advancedSettingInterface,
                FluentIcon.SETTING,
                tr["SubtitleExtractorGUI"]["Setting"],
                NavigationItemPosition.BOTTOM,
            ),
        ]

    def _wire_dashboard(self):
        dash = self.dashboardInterface
        dash.open_bg_remove.connect(lambda: self.switchTo(self.bgRemoveInterface))
        dash.open_video.connect(lambda: self.switchTo(self.homeInterface))
        dash.open_settings.connect(lambda: self.switchTo(self.advancedSettingInterface))
        dash.open_files.connect(self._dashboard_open_files)

    def _wire_settings(self):
        mgr = self.advancedSettingInterface.bg_remove_model_manager
        mgr.models_changed.connect(self.bgRemoveInterface.refresh_models)
        mgr.busy_changed.connect(self.bgRemoveInterface.set_install_busy)
        self.bgRemoveInterface.processing_changed.connect(mgr.set_processing)

    def _schedule_update_check(self):
        if not config.checkUpdateOnStartup.value:
            return
        self.check_update_timer = QtCore.QTimer(self)
        self.check_update_timer.setSingleShot(True)
        self.check_update_timer.timeout.connect(
            lambda: self.advancedSettingInterface.check_update(ignore=True)
        )
        self.check_update_timer.start(config.updateCheckDelayMs)

    def _show_restart_tooltip(self):
        InfoBar.success(
            "Updated successfully",
            "Configuration takes effect after restart",
            duration=config.restartTooltipDurationMs,
            parent=self,
        )

    def _dashboard_open_files(self):
        self.switchTo(self.bgRemoveInterface)
        self.bgRemoveInterface.open_file()

    def switchTo(self, interface):
        self._set_stacked_widget_instant(interface, popOut=False)

    def _set_stacked_widget_instant(self, widget, popOut=True):
        if isinstance(widget, QAbstractScrollArea):
            widget.verticalScrollBar().setValue(0)
        view = self.stackedWidget.view
        if view.currentWidget() is widget:
            return
        ani = getattr(view, "_ani", None)
        if ani is not None and ani.state() == QtCore.QAbstractAnimation.Running:
            ani.stop()
        QStackedWidget.setCurrentWidget(view, widget)

    def closeEvent(self, event):
        diag.start("window close - shutting down workers")
        try:
            from backend.tools.infer_client import InferClient

            InferClient.instance().shutdown()
        except Exception:
            pass
        # InferClient already stopped/unregistered the infer worker; sweep any leftovers
        ProcessManager.instance().terminate_all()
        diag.start("shutdown complete")
        super().closeEvent(event)

    def resizeEvent(self, event):
        QtWidgets.QWidget.resizeEvent(self, event)
        sync_header_geometry(self)

    def apply_default_window_geometry(self):
        self.center_window(config.windowW, config.windowH)

    def center_window(self, width=None, height=None):
        screen_rect = QtWidgets.QApplication.primaryScreen().availableGeometry()
        w = min(width if width is not None else config.windowW, screen_rect.width())
        h = min(height if height is not None else config.windowH, screen_rect.height())
        self.resize(w, h)
        frame = self.frameGeometry()
        frame.moveCenter(screen_rect.center())
        self.move(frame.topLeft())

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_C and event.modifiers() == QtCore.Qt.ControlModifier:
            diag.event("Ctrl+C - exiting")
            print("\nInterrupted by user (Ctrl+C), exiting...")
            self.close()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if not getattr(self, "_isResizeEnabled", True):
            return False

        et = event.type()
        if et not in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseMove):
            return False

        gp = event.globalPos()

        nav = self.navigationInterface
        if nav is not None and nav.isVisible():
            if nav.rect().contains(nav.mapFromGlobal(gp)):
                if et == QtCore.QEvent.Type.MouseMove:
                    self.unsetCursor()
                return False

        stacked = self.stackedWidget
        if stacked is not None and stacked.rect().contains(stacked.mapFromGlobal(gp)):
            if et == QtCore.QEvent.Type.MouseMove:
                self.unsetCursor()
            return False

        pos = gp - self.pos()
        border = 5
        edges = Qt.Edge(0)
        if pos.x() >= self.width() - border:
            edges |= Qt.RightEdge
        if pos.y() < border:
            edges |= Qt.TopEdge
        if pos.y() >= self.height() - border:
            edges |= Qt.BottomEdge

        if et == QtCore.QEvent.Type.MouseMove and self.windowState() == Qt.WindowNoState:
            if edges in (Qt.RightEdge | Qt.TopEdge,):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif edges in (Qt.RightEdge | Qt.BottomEdge,):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edges in (Qt.TopEdge, Qt.BottomEdge):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif edges == Qt.RightEdge:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.unsetCursor()
            return False

        if (
            obj in (self, self.titleBar)
            and et == QtCore.QEvent.Type.MouseButtonPress
            and edges
        ):
            from qframelesswindow.utils.linux_utils import LinuxMoveResize

            LinuxMoveResize.starSystemResize(self, gp, edges)
            return False

        return False


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    banner()
    diag.start("QApplication boot")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QtWidgets.QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    install_app_hooks(app)
    window = SubtitleExtractorGUI()
    install_window_hooks(window)
    window.show()
    window.apply_default_window_geometry()
    diag.start("window shown - event loop starting")
    app.exec()
    diag.start("event loop exited")
