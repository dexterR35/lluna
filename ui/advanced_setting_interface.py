"""Settings page - Midgard cards (same structure/bg as Home dashboard)."""

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import QFileDialog, QVBoxLayout
from qfluentwidgets import (
    ScrollArea,
    FluentIcon,
    MessageBox,
    SubtitleLabel,
    InfoBar,
    CaptionLabel,
)
from backend.config import config, tr, VERSION, PROJECT_HOME_URL, PROJECT_ISSUES_URL, PROJECT_RELEASES_URL
from backend.tools.config_section_reset import reset_section
from backend.tools.version_service import VersionService
from backend.tools.concurrent import TaskExecutor
from ui.component.utils.confirm_dialog import ask_confirm
from ui.component.cards.bg_remove_model_manager import BgRemoveModelManager
from ui.component.cards.enhance_model_manager import EnhanceModelManager
from ui.component.cards.low_light_model_manager import LowLightModelManager
from ui.component.cards.generate_model_manager import GenerateModelManager
from ui.component.cards.select_object_model_manager import SelectObjectModelManager
from ui.component.cards.model_install_helpers import (
    model_download_queue,
    register_queue_listener,
)
from backend.tools.first_run_downloads import pending_label
from backend.tools.model_download_registry import ModelDownloadRegistry, PendingDownload
from ui.component.cards.midgard_setting_cards import (
    MidgardCardGroup,
    MidgardHyperlinkCard,
    MidgardPushCard,
    MidgardRangeCard,
    MidgardSwitchCard,
)
from ui.component.cards.setting_card_style import apply_content_column_width
from ui.theme import SETTINGS


class AdvancedSettingInterface(ScrollArea):
    """Settings page - same Midgard CARD chrome as Home."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.version_manager = VersionService()
        self.__init_widgets()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        apply_content_column_width(
            self.contentColumn, self.viewport().width() - SETTINGS["margin"] * 2
        )

    def __init_widgets(self):
        self.scrollWidget = QtWidgets.QWidget(self)
        self.scrollWidget.setObjectName("SettingsScrollWidget")
        outer = QtWidgets.QHBoxLayout(self.scrollWidget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        self.contentColumn = QtWidgets.QWidget(self.scrollWidget)
        self.contentColumn.setObjectName("SettingsContentColumn")
        self.contentColumn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.expandLayout = QVBoxLayout(self.contentColumn)
        self.expandLayout.setSpacing(0)
        self.expandLayout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.contentColumn, 8)
        outer.addStretch(1)

        self.setWidget(self.scrollWidget)
        self.enableTransparentBackground()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setObjectName("AdvancedSettingInterface")

        self.setup_ui()
        self.setup_layout()

    def setup_layout(self):
        self.subtitle_detection_group.addSettingCard(self.subtitle_yx_axis_difference_pixel)
        self.subtitle_detection_group.addSettingCard(self.subtitle_area_deviation_pixel)
        self.subtitle_detection_group.addSettingCard(self.subtitle_area_y_axis_difference_pixel)
        self.subtitle_detection_group.addSettingCard(self.subtitle_area_pixel_tolerance_y_pixel)
        self.subtitle_detection_group.addSettingCard(self.subtitle_area_pixel_tolerance_x_pixel)
        self.subtitle_detection_group.addSettingCard(self.subtitle_timeline_backward_frame_count)
        self.subtitle_detection_group.addSettingCard(self.subtitle_timeline_forward_frame_count)
        self.expandLayout.addWidget(self.subtitle_detection_group)

        self.sttn_group.addSettingCard(self.sttn_neighbor_stride)
        self.sttn_group.addSettingCard(self.sttn_reference_length)
        self.sttn_group.addSettingCard(self.sttn_max_load_num)
        self.expandLayout.addWidget(self.sttn_group)

        self.propainter_group.addSettingCard(self.propainter_max_load_num)
        self.expandLayout.addWidget(self.propainter_group)

        for card in self.bg_remove_model_manager.cards:
            self.bg_remove_models_group.addSettingCard(card)
        self.expandLayout.addWidget(self.bg_remove_models_group)

        for card in self.enhance_model_manager.cards:
            self.enhance_models_group.addSettingCard(card)
        self.expandLayout.addWidget(self.enhance_models_group)

        for card in self.low_light_model_manager.cards:
            self.low_light_models_group.addSettingCard(card)
        self.expandLayout.addWidget(self.low_light_models_group)

        for card in self.generate_model_manager.cards:
            self.generate_models_group.addSettingCard(card)
        self.generate_models_group.addSettingCard(self.generate_model_manager.token_card)
        self.expandLayout.addWidget(self.generate_models_group)

        for card in self.select_object_model_manager.cards:
            self.select_object_models_group.addSettingCard(card)
        self.select_object_models_group.addSettingCard(self.select_object_more_complex)
        self.expandLayout.addWidget(self.select_object_models_group)

        self.advanced_group.addSettingCard(self.save_directory)
        self.advanced_group.addSettingCard(self.check_update_on_startup)
        self.expandLayout.addWidget(self.advanced_group)

        self.about_group.addSettingCard(self.feedback)
        self.about_group.addSettingCard(self.copyright)
        self.about_group.addSettingCard(self.project_link)
        self.expandLayout.addWidget(self.about_group)

        self.expandLayout.setSpacing(SETTINGS["spacing"])
        m = SETTINGS["margin"]
        self.expandLayout.setContentsMargins(
            m, m, m, SETTINGS["bottom"]
        )

    def setup_ui(self):
        self.page_title = SubtitleLabel(tr["SubtitleExtractorGUI"]["Setting"], self.contentColumn)
        self.expandLayout.addWidget(self.page_title)

        self.model_download_banner = CaptionLabel("", self.contentColumn)
        self.model_download_banner.setWordWrap(True)
        self.model_download_banner.hide()
        self.expandLayout.addWidget(self.model_download_banner)
        register_queue_listener(self._refresh_model_download_banner)

        self.subtitle_detection_group = MidgardCardGroup(
            tr["Setting"]["SubtitleDetectionSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["SubtitleDetectionSettingDesc"],
        )
        self.sttn_group = MidgardCardGroup(
            tr["Setting"]["SttnSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["SttnSettingDesc"],
        )
        self.propainter_group = MidgardCardGroup(
            tr["Setting"]["ProPainterSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["ProPainterSettingDesc"],
        )
        self.bg_remove_models_group = MidgardCardGroup(
            tr["Setting"]["BgRemoveModelsSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["BgRemoveModelsSettingDesc"],
        )
        self.bg_remove_model_manager = BgRemoveModelManager(self.bg_remove_models_group)
        self.bg_remove_model_manager.status_message.connect(self._on_bg_model_status)

        self.enhance_models_group = MidgardCardGroup(
            tr["Setting"]["EnhanceModelsSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["EnhanceModelsSettingDesc"],
        )
        self.enhance_model_manager = EnhanceModelManager(self.enhance_models_group)
        self.enhance_model_manager.status_message.connect(self._on_enhance_model_status)

        self.low_light_models_group = MidgardCardGroup(
            tr["Setting"]["LowLightModelsSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["LowLightModelsSettingDesc"],
        )
        self.low_light_model_manager = LowLightModelManager(self.low_light_models_group)
        self.low_light_model_manager.status_message.connect(self._on_low_light_model_status)

        self.generate_models_group = MidgardCardGroup(
            tr["Setting"]["GenerateModelsSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["GenerateModelsSettingDesc"],
        )
        self.generate_model_manager = GenerateModelManager(self.generate_models_group)
        self.generate_model_manager.status_message.connect(self._on_generate_model_status)

        self.select_object_models_group = MidgardCardGroup(
            tr["Setting"]["SelectObjectModelsSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["SelectObjectModelsSettingDesc"],
        )
        self.select_object_model_manager = SelectObjectModelManager(
            self.select_object_models_group
        )
        self.select_object_model_manager.status_message.connect(
            self._on_select_object_model_status
        )
        self.select_object_model_manager.models_changed.connect(
            self._sync_more_complex_switch
        )
        self.select_object_model_manager.busy_changed.connect(
            self._on_select_object_install_busy
        )
        self.select_object_more_complex = MidgardSwitchCard(
            configItem=config.selectObjectMoreComplex,
            icon=FluentIcon.IOT,
            title=tr["Setting"]["SelectObjectMoreComplex"],
            content=tr["Setting"]["SelectObjectMoreComplexDesc"],
            parent=self.select_object_models_group,
        )
        self.select_object_more_complex.checkedChanged.connect(
            self._on_select_object_more_complex_changed
        )

        self.advanced_group = MidgardCardGroup(
            tr["Setting"]["AdvancedSetting"],
            self.contentColumn,
            resettable=True,
            subtitle=tr["Setting"]["AdvancedSettingDesc"],
        )
        self.about_group = MidgardCardGroup(tr["Setting"]["AboutSetting"], self.contentColumn)

        self._wire_section_reset(
            self.subtitle_detection_group, "subtitle_detection", "SubtitleDetectionSetting"
        )
        self._wire_section_reset(self.sttn_group, "sttn", "SttnSetting")
        self._wire_section_reset(self.propainter_group, "propainter", "ProPainterSetting")
        self._wire_section_reset(
            self.bg_remove_models_group, "bg_remove_models", "BgRemoveModelsSetting"
        )
        self._wire_section_reset(
            self.enhance_models_group, "enhance_models", "EnhanceModelsSetting"
        )
        self._wire_section_reset(
            self.low_light_models_group, "low_light_models", "LowLightModelsSetting"
        )
        self._wire_section_reset(
            self.generate_models_group, "generate_models", "GenerateModelsSetting"
        )
        self._wire_section_reset(
            self.select_object_models_group,
            "select_object_models",
            "SelectObjectModelsSetting",
        )
        self._wire_section_reset(self.advanced_group, "advanced", "AdvancedSetting")

        self.subtitle_yx_axis_difference_pixel = MidgardRangeCard(
            configItem=config.subtitleYXAxisDifferencePixel,
            icon=FluentIcon.ZOOM,
            title=tr["Setting"]["SubtitleYXAxisDifferencePixel"],
            content=tr["Setting"]["SubtitleYXAxisDifferencePixelDesc"],
            parent=self.subtitle_detection_group,
        )
        self.subtitle_area_deviation_pixel = MidgardRangeCard(
            configItem=config.subtitleAreaDeviationPixel,
            icon=FluentIcon.ZOOM_IN,
            title=tr["Setting"]["SubtitleAreaDeviationPixel"],
            content=tr["Setting"]["SubtitleAreaDeviationPixelDesc"],
            parent=self.subtitle_detection_group,
        )
        self.subtitle_area_y_axis_difference_pixel = MidgardRangeCard(
            configItem=config.subtitleAreaYAxisDifferencePixel,
            icon=FluentIcon.ALIGNMENT,
            title=tr["Setting"]["SubtitleAreaYAxisDifferencePixel"],
            content=tr["Setting"]["SubtitleAreaYAxisDifferencePixelDesc"],
            parent=self.subtitle_detection_group,
        )
        self.subtitle_area_pixel_tolerance_y_pixel = MidgardRangeCard(
            configItem=config.subtitleAreaPixelToleranceYPixel,
            icon=FluentIcon.UP,
            title=tr["Setting"]["SubtitleAreaPixelToleranceYPixel"],
            content=tr["Setting"]["SubtitleAreaPixelToleranceYPixelDesc"],
            parent=self.subtitle_detection_group,
        )
        self.subtitle_area_pixel_tolerance_x_pixel = MidgardRangeCard(
            configItem=config.subtitleAreaPixelToleranceXPixel,
            icon=FluentIcon.RIGHT_ARROW,
            title=tr["Setting"]["SubtitleAreaPixelToleranceXPixel"],
            content=tr["Setting"]["SubtitleAreaPixelToleranceXPixelDesc"],
            parent=self.subtitle_detection_group,
        )
        self.subtitle_timeline_backward_frame_count = MidgardRangeCard(
            configItem=config.subtitleTimelineBackwardFrameCount,
            icon=FluentIcon.PAGE_LEFT,
            title=tr["Setting"]["SubtitleTimelineBackwardFrameCount"],
            content=tr["Setting"]["SubtitleTimelineBackwardFrameCountDesc"],
            parent=self.subtitle_detection_group,
        )
        self.subtitle_timeline_forward_frame_count = MidgardRangeCard(
            configItem=config.subtitleTimelineForwardFrameCount,
            icon=FluentIcon.PAGE_RIGHT,
            title=tr["Setting"]["SubtitleTimelineForwardFrameCount"],
            content=tr["Setting"]["SubtitleTimelineForwardFrameCountDesc"],
            parent=self.subtitle_detection_group,
        )

        self.sttn_neighbor_stride = MidgardRangeCard(
            configItem=config.sttnNeighborStride,
            icon=FluentIcon.UNIT,
            title=tr["Setting"]["SttnNeighborStride"],
            content=tr["Setting"]["SttnNeighborStrideDesc"],
            parent=self.sttn_group,
        )
        self.sttn_reference_length = MidgardRangeCard(
            configItem=config.sttnReferenceLength,
            icon=FluentIcon.MORE,
            title=tr["Setting"]["SttnReferenceLength"],
            content=tr["Setting"]["SttnReferenceLengthDesc"],
            parent=self.sttn_group,
        )
        self.sttn_max_load_num = MidgardRangeCard(
            configItem=config.sttnMaxLoadNum,
            icon=FluentIcon.DICTIONARY,
            title=tr["Setting"]["SttnMaxLoadNum"],
            content=tr["Setting"]["SttnMaxLoadNumDesc"],
            parent=self.sttn_group,
        )
        self.propainter_max_load_num = MidgardRangeCard(
            configItem=config.propainterMaxLoadNum,
            icon=FluentIcon.DICTIONARY,
            title=tr["Setting"]["PropainterMaxLoadNum"],
            content=tr["Setting"]["PropainterMaxLoadNumDesc"],
            parent=self.propainter_group,
        )

        self.save_directory = MidgardPushCard(
            text=tr["Setting"]["ChooseDirectory"],
            icon=FluentIcon.DOWNLOAD,
            title=tr["Setting"]["SaveDirectory"],
            content=self._save_directory_content(),
            parent=self.advanced_group,
        )
        self.save_directory.clicked.connect(self.choose_save_directory)

        self.check_update_on_startup = MidgardSwitchCard(
            icon=FluentIcon.UPDATE,
            title=tr["Setting"]["CheckUpdateOnStartup"],
            content=tr["Setting"]["CheckUpdateOnStartupDesc"],
            configItem=config.checkUpdateOnStartup,
            parent=self.advanced_group,
        )

        self.feedback = MidgardPushCard(
            text=tr["Setting"]["FeedbackButton"],
            icon=FluentIcon.MAIL,
            title=tr["Setting"]["FeedbackTitle"],
            content=tr["Setting"]["FeedbackDesc"],
            parent=self.about_group,
            primary=True,
        )
        self.feedback.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(PROJECT_ISSUES_URL))
        )

        self.copyright = MidgardPushCard(
            text=tr["Setting"]["CopyrightButton"],
            icon=FluentIcon.MAIL,
            title=tr["Setting"]["CopyrightTitle"],
            content=tr["Setting"]["CopyrightDesc"].format(VERSION),
            parent=self.about_group,
            primary=True,
        )
        self.copyright.clicked.connect(lambda: self.check_update())

        self.project_link = MidgardHyperlinkCard(
            url=PROJECT_HOME_URL,
            text=PROJECT_HOME_URL,
            icon=FluentIcon.GITHUB,
            title=tr["Setting"]["ProjectLinkTitle"],
            content=tr["Setting"]["ProjectLinkDesc"],
            parent=self.about_group,
        )

    def _save_directory_content(self) -> str:
        text = tr["Setting"]["SaveDirectoryDesc"]
        folder = config.saveDirectory.value
        if folder:
            text = f"{text}\n{tr['Setting']['SaveDirectoryCurrent'].format(folder)}"
        else:
            text = f"{text}\n{tr['Setting']['SaveDirectoryDefault']}"
        return text

    def _wire_section_reset(self, group: MidgardCardGroup, section_id: str, title_key: str):
        group.resetClicked.connect(
            lambda _checked=False, sid=section_id, key=title_key: self._reset_section(sid, key)
        )

    def _reset_section(self, section_id: str, title_key: str):
        section_name = tr["Setting"][title_key]
        if not ask_confirm(
            tr["Setting"]["ResetSectionConfirmTitle"],
            tr["Setting"]["ResetSectionConfirmDesc"].format(section_name),
            self.window(),
        ):
            return
        reset_section(section_id)
        if section_id == "advanced":
            self.save_directory.setContent(self._save_directory_content())
        if section_id == "bg_remove_models":
            self.bg_remove_model_manager.refresh()
        elif section_id == "enhance_models":
            self.enhance_model_manager.refresh()
        elif section_id == "low_light_models":
            self.low_light_model_manager.refresh()
        elif section_id == "generate_models":
            self.generate_model_manager.refresh()
        elif section_id == "select_object_models":
            config.set(config.selectObjectMoreComplex, False)
            self.select_object_model_manager.refresh()
        InfoBar.success(
            title=section_name,
            content=tr["Setting"]["ResetSectionDone"],
            duration=config.infoBarDurationMs,
            parent=self,
        )

    def show_message_box(self, title: str, content: str, showYesButton=False, yesSlot=None):
        w = MessageBox(title, content, self)
        if not showYesButton:
            w.cancelButton.setText(self.tr("Close"))
            w.yesButton.hide()
            w.buttonLayout.insertStretch(0, 1)
        if w.exec() and yesSlot is not None:
            yesSlot()

    def check_update(self, ignore=False):
        TaskExecutor.runTask(self.version_manager.has_new_version).then(
            lambda success: self.on_version_info_fetched(success, ignore)
        )

    def on_version_info_fetched(self, success, ignore=False):
        if success:
            self.show_message_box(
                tr["Setting"]["UpdatesAvailableTitle"],
                tr["Setting"]["UpdatesAvailableDesc"].format(self.version_manager.lastest_version),
                True,
                lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(PROJECT_RELEASES_URL)),
            )
        elif not ignore:
            self.show_message_box(
                tr["Setting"]["NoUpdatesAvailableTitle"],
                tr["Setting"]["NoUpdatesAvailableDesc"],
            )

    def choose_save_directory(self):
        last_save_directory = "./" if not config.saveDirectory.value else config.saveDirectory.value
        folder = QFileDialog.getExistingDirectory(
            self, tr["Setting"]["ChooseDirectory"], last_save_directory
        )
        if not folder:
            folder = ""
        config.set(config.saveDirectory, folder)
        self.save_directory.setContent(self._save_directory_content())

    def showEvent(self, event):
        super().showEvent(event)
        self.bg_remove_model_manager.refresh()
        self.enhance_model_manager.refresh()
        self.select_object_model_manager.refresh()
        self.low_light_model_manager.refresh()
        self.generate_model_manager.refresh()
        self._sync_more_complex_switch()

    def _on_select_object_install_busy(self, busy: bool):
        self.select_object_more_complex.switchButton.setEnabled(
            not busy and self._complex_pair_ready()
        )

    def _complex_pair_ready(self) -> bool:
        from backend.tools.select_object_models import is_complex_pair_installed

        return is_complex_pair_installed()

    def _sync_more_complex_switch(self):
        from backend.tools.select_object_models import is_complex_pair_installed

        self.select_object_more_complex.setContent(
            tr["Setting"]["SelectObjectMoreComplexDesc"]
        )

        ready = is_complex_pair_installed()
        enabled = ready and not self.select_object_model_manager.is_busy
        self.select_object_more_complex.switchButton.setEnabled(enabled)
        if not ready and config.selectObjectMoreComplex.value:
            config.set(config.selectObjectMoreComplex, False)
            self.select_object_more_complex.setChecked(False)

    def _on_select_object_more_complex_changed(self, checked: bool):
        from backend.tools.select_object_models import is_complex_pair_installed

        if checked and not is_complex_pair_installed():
            config.set(config.selectObjectMoreComplex, False)
            self.select_object_more_complex.blockSignals(True)
            self.select_object_more_complex.setChecked(False)
            self.select_object_more_complex.blockSignals(False)
            InfoBar.warning(
                title=tr["Setting"]["SelectObjectModelsSetting"],
                content=tr["SelectObject"].get(
                    "ComplexNeedsInstall",
                    "Install the More complex models first.",
                ),
                duration=config.infoBarDurationMs,
                parent=self,
            )

    def _refresh_model_download_banner(self) -> None:
        st = tr["Setting"]
        queue = model_download_queue()
        pending = ModelDownloadRegistry.instance().list_pending()
        current = queue.current_job()

        if not queue.is_busy() and not pending:
            self.model_download_banner.hide()
            return

        if current:
            kind, key = current
            name = pending_label(PendingDownload(kind, key))
            n = max(len(pending), 1)
            self.model_download_banner.setText(
                st.get(
                    "ModelDownloadBannerActive",
                    "Downloading: {} ({} in queue, one at a time)",
                ).format(name, n)
            )
        else:
            self.model_download_banner.setText(
                st.get(
                    "ModelDownloadBannerPending",
                    "{} model(s) queued — downloads start one at a time.",
                ).format(len(pending))
            )
        self.model_download_banner.show()

    def _on_select_object_model_status(self, message: str):
        InfoBar.info(
            title=tr["Setting"]["SelectObjectModelsSetting"],
            content=message,
            duration=config.infoBarDurationMs,
            parent=self,
        )
        self._sync_more_complex_switch()

    def _on_bg_model_status(self, message: str):
        InfoBar.info(
            title=tr["Setting"]["BgRemoveModelsSetting"],
            content=message,
            duration=config.infoBarDurationMs,
            parent=self,
        )

    def _on_enhance_model_status(self, message: str):
        InfoBar.info(
            title=tr["Setting"]["EnhanceModelsSetting"],
            content=message,
            duration=config.infoBarDurationMs,
            parent=self,
        )

    def _on_low_light_model_status(self, message: str):
        InfoBar.info(
            title=tr["Setting"]["LowLightModelsSetting"],
            content=message,
            duration=config.infoBarDurationMs,
            parent=self,
        )

    def _on_generate_model_status(self, message: str):
        InfoBar.info(
            title=tr["Setting"]["GenerateModelsSetting"],
            content=message,
            duration=config.infoBarDurationMs,
            parent=self,
        )
