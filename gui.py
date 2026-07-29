# -*- coding: utf-8 -*-
"""Midgard main window - header + nav shell, stacked tool pages."""

import sys
import os
import multiprocessing
import threading

from backend.tools.diag import banner
from backend.tools import diag

from PySide6.QtCore import Qt
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QStackedWidget, QAbstractScrollArea

from backend.config import config, tr, VERSION
from qfluentwidgets import FluentWindow, FluentIcon, NavigationItemPosition, InfoBar

from backend.tools.process_manager import ProcessManager
from ui.diag_hooks import install_app_hooks, install_window_hooks
from ui.shell import (
    APP_ICON,
    HEADER_H,
    NavRoute,
    apply_shell,
    configure_header,
    enable_instant_page_switch,
    register_routes,
    setup_nav,
    sync_header_geometry,
)


class SubtitleExtractorGUI(FluentWindow):
    service_start_failed = QtCore.Signal(str)
    update_available = QtCore.Signal(str, str)

    def __init__(self):
        super().__init__()
        self._shutdown_complete = False
        self._deferred_started = False
        self._shutdown_event = threading.Event()
        self._startup_thread = None
        self._settings_wired: set[str] = set()
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
        self._wire_gpu_busy_gate()
        apply_shell(self)
        from ui.component.model_download_panel import ModelDownloadPanel

        self.modelDownloadPanel = ModelDownloadPanel(self)
        self.modelDownloadPanel.layout_changed.connect(
            self._position_model_download_panel
        )
        self._position_model_download_panel()
        config.appRestartSig.connect(self._show_restart_tooltip)
        self.service_start_failed.connect(self._show_service_failure)
        self.update_available.connect(self._show_update_available)
        diag.start("main window shell ready")

    def start_deferred_services(self):
        """Run service startup only after the window has had a chance to paint."""
        if self._deferred_started or self._shutdown_complete:
            return
        self._deferred_started = True
        diag.start("deferred services starting")
        self._schedule_update_check()
        QtCore.QTimer.singleShot(0, self._restart_pending_downloads)
        self._startup_thread = threading.Thread(
            target=self._start_background_services,
            daemon=True,
            name="startup-services",
        )
        self._startup_thread.start()
        diag.start("main window interactive; background services starting")

    def _start_background_services(self):
        """Initialize non-Qt services without blocking the GUI thread."""
        try:
            from backend.tools.hf_auth import apply_hf_token_to_env

            apply_hf_token_to_env()
        except Exception as exc:
            diag.warn(f"Hugging Face credential setup unavailable: {type(exc).__name__}")
        if self._shutdown_event.is_set():
            return
        try:
            from backend.tools.soft_defaults import apply_soft_defaults_if_needed

            apply_soft_defaults_if_needed()
        except Exception as exc:
            diag.warn(f"hardware defaults unavailable: {type(exc).__name__}")
        if self._shutdown_event.is_set():
            return
        try:
            from backend.tools.infer_client import InferClient

            InferClient.instance().ensure_started()
        except Exception as e:
            diag.error(f"infer worker failed to start  {e}")
            self.service_start_failed.emit(type(e).__name__)
        if self._shutdown_event.is_set():
            try:
                from backend.tools.infer_client import InferClient

                InferClient.instance().shutdown()
            except Exception:
                pass
            return
        try:
            from backend.tools.diag_health import report_startup

            report_startup()
        except Exception as e:
            diag.warn(f"startup health check failed  {e}")
        try:
            from backend.media.workspace import cleanup_stale_workspaces

            cleanup_stale_workspaces()
        except Exception as e:
            diag.warn(f"temporary workspace cleanup failed  {e}")
        diag.start("background services ready (hardware + infer worker)")

    def _build_pages(self) -> list[NavRoute]:
        from ui.dashboard_interface import DashboardInterface
        from ui.component.lazy_page import LazyPage

        self.dashboardInterface = DashboardInterface(self)
        self.dashboardInterface.setObjectName("DashboardInterface")
        self.bgRemoveInterface = LazyPage(
            "BgRemoveInterface",
            self._create_bg_remove_page,
            self,
        )
        self.upscaleInterface = LazyPage(
            "UpscaleInterface",
            self._create_upscale_page,
            self,
        )
        self.lowLightInterface = LazyPage(
            "LowLightInterface",
            self._create_low_light_page,
            self,
        )
        self.homeInterface = LazyPage(
            "HomeInterface",
            self._create_subtitle_page,
            self,
        )
        self.advancedSettingInterface = LazyPage(
            "AdvancedSettingInterface",
            self._create_settings_page,
            self,
        )
        for page in (
            self.bgRemoveInterface,
            self.upscaleInterface,
            self.lowLightInterface,
            self.homeInterface,
            self.advancedSettingInterface,
        ):
            page.failed.connect(self._show_feature_failure)

        return [
            NavRoute(
                self.dashboardInterface,
                FluentIcon.HOME,
                tr["HomeDashboard"]["TabTitle"],
            ),
            NavRoute(
                self.upscaleInterface,
                FluentIcon.ZOOM,
                tr["Upscale"]["Title"],
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
                self.lowLightInterface,
                FluentIcon.BRIGHTNESS,
                tr["LowLight"]["Title"],
            ),
            NavRoute(
                self.advancedSettingInterface,
                FluentIcon.SETTING,
                tr["SubtitleExtractorGUI"]["Setting"],
                NavigationItemPosition.BOTTOM,
            ),
        ]

    def _create_bg_remove_page(self):
        from ui.bg_remove_interface import BgRemoveInterface

        page = BgRemoveInterface(self)
        page.install_models_requested.connect(
            lambda: self._open_model_settings("bg_remove_models_group")
        )
        return page

    def _create_upscale_page(self):
        from ui.upscale_interface import UpscaleInterface

        page = UpscaleInterface(self)
        page.install_models_requested.connect(
            lambda: self._open_model_settings("enhance_models_group")
        )
        return page

    def _create_low_light_page(self):
        from ui.low_light_interface import LowLightInterface

        page = LowLightInterface(self)
        page.install_models_requested.connect(
            lambda: self._open_model_settings("low_light_models_group")
        )
        return page

    def _create_subtitle_page(self):
        from ui.home_interface import HomeInterface

        return HomeInterface(self)

    def _create_settings_page(self):
        from ui.advanced_setting_interface import AdvancedSettingInterface

        page = AdvancedSettingInterface(self)
        page.setObjectName("AdvancedSettingInterfaceContent")
        return page

    def _wire_dashboard(self):
        dash = self.dashboardInterface
        dash.open_generate_settings.connect(
            lambda: self._open_model_settings("generate_models_group")
        )
        dash.open_files.connect(self._dashboard_open_files)

    def _open_model_settings(self, group_name: str):
        """Open Settings and reveal the requested model manager group."""
        settings = self.advancedSettingInterface.ensure_loaded()
        if settings is None:
            return
        self.switchTo(self.advancedSettingInterface)
        group = getattr(settings, group_name, None)
        if group is not None:
            expand = getattr(group, "setCollapsed", None)
            if callable(expand):
                expand(False)
            QtCore.QTimer.singleShot(
                0,
                lambda page=settings, target=group: page.ensureWidgetVisible(
                    target, 0, 24
                ),
            )

    def _wire_settings(self):
        pages = (
            self.bgRemoveInterface,
            self.upscaleInterface,
            self.lowLightInterface,
            self.advancedSettingInterface,
        )
        for page in pages:
            page.loaded.connect(lambda _content: self._try_wire_settings())
        self._try_wire_settings()

    def _try_wire_settings(self):
        settings = self.advancedSettingInterface.content
        if settings is None:
            return
        if "generate" not in self._settings_wired:
            manager = settings.generate_model_manager
            manager.models_changed.connect(
                self.dashboardInterface.refresh_generate_gate
            )
            self.dashboardInterface.processing_changed.connect(
                manager.set_processing
            )
            self._settings_wired.add("generate")
        feature_pairs = (
            (
                "background",
                self.bgRemoveInterface,
                settings.bg_remove_model_manager,
            ),
            (
                "upscale",
                self.upscaleInterface,
                settings.enhance_model_manager,
            ),
            (
                "low_light",
                self.lowLightInterface,
                settings.low_light_model_manager,
            ),
        )
        for key, lazy_page, manager in feature_pairs:
            feature = lazy_page.content
            if feature is None or key in self._settings_wired:
                continue
            manager.models_changed.connect(feature.refresh_models)
            manager.busy_changed.connect(feature.set_install_busy)
            feature.processing_changed.connect(manager.set_processing)
            self._settings_wired.add(key)

    def _wire_gpu_busy_gate(self):
        """One shared infer worker: when any tool runs, lock every other tool."""
        self._gpu_tools = [self.dashboardInterface]

        def _on_busy(busy: bool, source):
            for tool in tuple(self._gpu_tools):
                if tool is source:
                    continue
                setter = getattr(tool, "set_external_gpu_busy", None)
                if callable(setter):
                    setter(bool(busy))

        def register(tool):
            if tool in self._gpu_tools:
                return
            self._gpu_tools.append(tool)
            signal = getattr(tool, "processing_changed", None)
            if signal is None:
                return
            signal.connect(lambda busy, src=tool: _on_busy(busy, src))

        dashboard_signal = getattr(
            self.dashboardInterface, "processing_changed", None
        )
        if dashboard_signal is not None:
            dashboard_signal.connect(
                lambda busy, src=self.dashboardInterface: _on_busy(busy, src)
            )
        for lazy_page in (
            self.bgRemoveInterface,
            self.upscaleInterface,
            self.lowLightInterface,
            self.homeInterface,
        ):
            lazy_page.loaded.connect(register)

    def _schedule_update_check(self):
        if not config.checkUpdateOnStartup.value:
            return
        self.check_update_timer = QtCore.QTimer(self)
        self.check_update_timer.setSingleShot(True)
        self.check_update_timer.timeout.connect(self._start_update_check)
        self.check_update_timer.start(config.updateCheckDelayMs)

    def _start_update_check(self):
        def check():
            from backend.updates.service import check_for_update

            result = check_for_update()
            if result.available and not self._shutdown_event.is_set():
                self.update_available.emit(
                    result.latest_version,
                    result.release_url,
                )

        threading.Thread(
            target=check,
            daemon=True,
            name="update-check",
        ).start()

    def _restart_pending_downloads(self):
        if self._shutdown_complete:
            return
        try:
            from backend.tools.model_download_lifecycle import (
                prepare_restart_pending,
                restart_pending_downloads,
            )

            if not prepare_restart_pending():
                return
            settings = self.advancedSettingInterface.ensure_loaded()
            if settings is not None:
                restart_pending_downloads(settings)
        except Exception as exc:
            diag.warn(
                f"pending model download restart failed  {type(exc).__name__}"
            )

    def _show_restart_tooltip(self):
        InfoBar.success(
            "Updated successfully",
            "Configuration takes effect after restart",
            duration=config.restartTooltipDurationMs,
            parent=self,
        )

    def _show_service_failure(self, detail: str):
        InfoBar.error(
            "Processing service unavailable",
            "Midgard opened in degraded mode. Open Diagnostics or restart "
            f"the application. ({detail})",
            duration=max(config.infoBarDurationMs, 7000),
            parent=self,
        )

    def _show_feature_failure(self, detail: str):
        InfoBar.error(
            "Feature unavailable",
            f"This page could not be loaded. Technical detail: {detail}",
            duration=max(config.infoBarDurationMs, 7000),
            parent=self,
        )

    def _show_update_available(self, version: str, _url: str):
        InfoBar.info(
            "Update available",
            f"Midgard {version} is available. Open Settings for release details.",
            duration=max(config.infoBarDurationMs, 7000),
            parent=self,
        )

    def _dashboard_open_files(self):
        self.switchTo(self.bgRemoveInterface)
        feature = self.bgRemoveInterface.ensure_loaded()
        if feature is not None:
            feature.open_file()

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
        self._shutdown_workers()
        super().closeEvent(event)

    def _shutdown_workers(self):
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        self._shutdown_event.set()
        diag.start("window close - shutting down workers")
        timer = getattr(self, "check_update_timer", None)
        if timer is not None:
            timer.stop()
        try:
            from backend.tools.model_download_lifecycle import abort_downloads_on_shutdown

            # Stop downloads, delete partials; reopen will start over (not resume)
            abort_downloads_on_shutdown()
        except Exception as exc:
            diag.warn(f"download shutdown failed: {type(exc).__name__}")
        try:
            from backend.tools.infer_client import InferClient

            InferClient.instance().shutdown()
        except Exception as exc:
            diag.warn(f"inference shutdown failed: {type(exc).__name__}")
        # InferClient already stopped/unregistered the infer worker; sweep any leftovers
        ProcessManager.instance().terminate_all()
        startup_thread = self._startup_thread
        if (
            startup_thread is not None
            and startup_thread is not threading.current_thread()
            and startup_thread.is_alive()
        ):
            startup_thread.join(timeout=3.0)
        diag.start("shutdown complete")

    def resizeEvent(self, event):
        QtWidgets.QWidget.resizeEvent(self, event)
        sync_header_geometry(self)
        self._position_model_download_panel()

    def _position_model_download_panel(self):
        panel = getattr(self, "modelDownloadPanel", None)
        if panel is None:
            return
        margin = 16
        panel.move(
            max(margin, self.width() - panel.width() - margin),
            max(HEADER_H + margin, self.height() - panel.height() - margin),
        )
        if panel.isVisible():
            panel.raise_()

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


def create_application(argv=None):
    existing = QtWidgets.QApplication.instance()
    if existing is not None:
        return existing
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QtWidgets.QApplication(sys.argv if argv is None else argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    return app


def main(argv=None) -> int:
    if os.environ.get("MIDGARD_BOOTSTRAPPED") != "1":
        from backend.application.bootstrap import prepare_desktop

        prepare_desktop(argv)
    if multiprocessing.get_start_method(allow_none=True) is None:
        multiprocessing.set_start_method("spawn")
    banner()
    diag.start("QApplication boot")
    app = create_application(argv)
    install_app_hooks(app)
    window = SubtitleExtractorGUI()
    install_window_hooks(window)
    app.aboutToQuit.connect(window._shutdown_workers)
    window.show()
    window.apply_default_window_geometry()
    QtCore.QTimer.singleShot(0, window.start_deferred_services)
    diag.start("window shown - event loop starting")
    exit_code = app.exec()
    diag.start("event loop exited")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
