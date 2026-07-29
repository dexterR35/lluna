"""Advanced Settings cards - same MidgardSettingCard structure/bg as Home dashboard."""

from __future__ import annotations

from typing import Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, FluentIconBase, HyperlinkButton, SwitchButton, qconfig
from qfluentwidgets.components.widgets.switch_button import IndicatorPosition

from backend.config import tr
from backend.tools.setting_risk import RiskLevel, assess_setting_risk
from ui.component.cards.midgard_card import MidgardSettingCard
from ui.component.controls.button_styles import make_button
from ui.component.controls.slider_styles import PrimarySlider
from ui.theme import CARD, SETTINGS, STATUS, TEXT, TEXT_SECONDARY


class MidgardCardGroup(QWidget):
    """Collapsible section title + stacked Midgard cards."""

    resetClicked = Signal()
    collapsedChanged = Signal(bool)

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        resettable: bool = False,
        subtitle: str = "",
        collapsed: bool = True,
    ):
        super().__init__(parent)
        self._title = title
        self._collapsed = False
        self.setObjectName("MidgardCardGroup")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SETTINGS["group_spacing"])

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.titleButton = QToolButton(self)
        self.titleButton.setObjectName("MidgardCardGroupTitle")
        self.titleButton.setText(title)
        self.titleButton.setCheckable(True)
        self.titleButton.setAutoRaise(True)
        self.titleButton.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.titleButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.titleButton.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.titleButton.setAccessibleName(f"{title} section")
        self.titleButton.setStyleSheet(
            f"""
            QToolButton#MidgardCardGroupTitle {{
                color: {TEXT_SECONDARY};
                font-size: {SETTINGS['group_title_size']}px;
                font-weight: {SETTINGS['group_title_weight']};
                background: transparent;
                border: none;
                padding: 3px 0;
                text-align: left;
            }}
            QToolButton#MidgardCardGroupTitle:hover {{
                color: {TEXT};
            }}
            """
        )
        self.titleButton.clicked.connect(
            lambda expanded: self.setCollapsed(not expanded)
        )
        # Backward-compatible attribute for callers that customize the title.
        self.titleLabel = self.titleButton
        header.addWidget(self.titleButton, 1)

        root.addLayout(header)

        if subtitle:
            self.titleButton.setToolTip(subtitle)

        self.cardHost = QWidget(self)
        self.cardHostLayout = QVBoxLayout(self.cardHost)
        self.cardHostLayout.setContentsMargins(0, 0, 0, 0)
        self.cardHostLayout.setSpacing(SETTINGS["card_stack_spacing"])

        self.cardsContainer = QWidget(self.cardHost)
        self.cardLayout = QVBoxLayout(self.cardsContainer)
        self.cardLayout.setContentsMargins(0, 0, 0, 0)
        self.cardLayout.setSpacing(SETTINGS["card_stack_spacing"])
        self.cardHostLayout.addWidget(self.cardsContainer)

        self.resetButton = None
        if resettable:
            resetRow = QWidget(self.cardHost)
            resetLayout = QHBoxLayout(resetRow)
            resetLayout.setContentsMargins(0, 4, 0, 0)
            resetLayout.setSpacing(0)
            resetLayout.addStretch(1)
            self.resetButton = make_button(
                tr["Setting"]["ResetSection"],
                "secondary",
                resetRow,
                FluentIcon.SYNC,
                size="small",
            )
            self.resetButton.clicked.connect(self.resetClicked.emit)
            resetLayout.addWidget(self.resetButton)
            self.cardHostLayout.addWidget(resetRow)

        root.addWidget(self.cardHost)
        self.setCollapsed(collapsed, emit=False)

    def addSettingCard(self, card: QWidget):
        self.cardLayout.addWidget(card)

    def isCollapsed(self) -> bool:
        return self._collapsed

    def setCollapsed(self, collapsed: bool, *, emit: bool = True) -> None:
        collapsed = bool(collapsed)
        changed = collapsed != self._collapsed
        self._collapsed = collapsed
        self.cardHost.setVisible(not collapsed)
        self.titleButton.blockSignals(True)
        self.titleButton.setChecked(not collapsed)
        self.titleButton.blockSignals(False)
        self.titleButton.setArrowType(
            Qt.ArrowType.RightArrow if collapsed else Qt.ArrowType.DownArrow
        )
        state = "collapsed" if collapsed else "expanded"
        self.titleButton.setAccessibleDescription(
            f"{self._title} section, {state}"
        )
        if changed and emit:
            self.collapsedChanged.emit(collapsed)

    def toggleCollapsed(self) -> None:
        self.setCollapsed(not self._collapsed)


def _risk_badge_style(level: RiskLevel) -> str:
    if level == "none":
        return ""
    color = STATUS["warning"] if level == "caution" else STATUS["error"]
    s = SETTINGS
    return (
        f"color: {color}; background: transparent; border: 1px solid {color}; "
        f"border-radius: {s['risk_badge_radius']}px; "
        f"font-size: {s['risk_badge_size']}px; font-weight: 600; "
        f"padding: 1px {s['risk_badge_pad_x']}px;"
    )


class MidgardRangeCard(MidgardSettingCard):
    """Slider row - same shell as dashboard InfoSettingCard."""

    valueChanged = Signal(int)

    def __init__(
        self,
        configItem,
        icon: Union[str, QIcon, FluentIconBase],
        title: str,
        content: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(icon, title, content, parent, detailed=True)
        self.configItem = configItem
        self.valueLabel = QLabel(str(configItem.value), self)
        self.valueLabel.setObjectName("valueLabel")
        self.valueLabel.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self.riskLabel = QLabel("", self)
        self.riskLabel.setObjectName("riskLabel")
        self.riskLabel.hide()
        self.slider = PrimarySlider(Qt.Orientation.Horizontal, self)
        self.slider.setMinimumWidth(CARD["slider_min_w"])
        self.slider.setSingleStep(1)
        self.slider.setRange(*configItem.range)
        self.slider.setValue(configItem.value)

        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(CARD["value_gap"])
        self.hBoxLayout.addWidget(self.riskLabel, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(CARD["value_gap"])
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(CARD["control_gap"])

        configItem.valueChanged.connect(self.setValue)
        self.slider.valueChanged.connect(self._on_slider)
        self._update_risk_indicator(configItem.value)

    def _update_risk_indicator(self, value: int):
        level, hint_key = assess_setting_risk(self.configItem, value)
        if level == "none":
            self.riskLabel.hide()
            self.riskLabel.setToolTip("")
            self.valueLabel.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            return

        label = (
            tr["Setting"]["SettingRiskHigh"]
            if level == "high"
            else tr["Setting"]["SettingRiskCaution"]
        )
        self.riskLabel.setText(label)
        self.riskLabel.setStyleSheet(_risk_badge_style(level))
        hint = tr["Setting"].get(hint_key or "", tr["Setting"]["SettingRiskHintGeneric"])
        self.riskLabel.setToolTip(hint)
        color = STATUS["error"] if level == "high" else STATUS["warning"]
        self.valueLabel.setStyleSheet(f"color: {color}; background: transparent; font-weight: 600;")
        self.riskLabel.show()
        self.riskLabel.adjustSize()

    def _on_slider(self, value: int):
        self.setValue(value)
        self.valueChanged.emit(value)

    def setValue(self, value: int):
        qconfig.set(self.configItem, value)
        self.valueLabel.setNum(value)
        self.valueLabel.adjustSize()
        self._update_risk_indicator(value)
        if self.slider.value() != value:
            self.slider.blockSignals(True)
            self.slider.setValue(value)
            self.slider.blockSignals(False)


class MidgardSwitchCard(MidgardSettingCard):
    """On/Off row - same shell as dashboard cards."""

    checkedChanged = Signal(bool)

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase],
        title: str,
        content: str = "",
        configItem=None,
        parent: QWidget | None = None,
    ):
        super().__init__(icon, title, content, parent, detailed=True)
        self.configItem = configItem
        self.switchButton = SwitchButton("Off", self, IndicatorPosition.RIGHT)
        self.switchButton.setOnText("On")
        self.switchButton.setOffText("Off")
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(CARD["control_gap"])

        if configItem is not None:
            self.setValue(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setValue)
        self.switchButton.checkedChanged.connect(self._on_checked)

    def _on_checked(self, checked: bool):
        self.setValue(checked)
        self.checkedChanged.emit(checked)

    def setValue(self, checked: bool):
        if self.configItem is not None:
            qconfig.set(self.configItem, checked)
        self.switchButton.blockSignals(True)
        self.switchButton.setChecked(bool(checked))
        self.switchButton.blockSignals(False)
        self.switchButton.setText("On" if checked else "Off")


class MidgardPushCard(MidgardSettingCard):
    """Action button row - secondary theme button."""

    clicked = Signal()

    def __init__(
        self,
        text: str,
        icon: Union[str, QIcon, FluentIconBase],
        title: str,
        content: str = "",
        parent: QWidget | None = None,
        *,
        primary: bool = False,
    ):
        super().__init__(icon, title, content, parent, detailed=True)
        role = "primary" if primary else "secondary"
        self.button = make_button(text, role, self)
        self.hBoxLayout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(CARD["control_gap"])
        self.button.clicked.connect(self.clicked.emit)


class MidgardHyperlinkCard(MidgardSettingCard):
    """Link row - opens URL."""

    def __init__(
        self,
        url: str,
        text: str,
        icon: Union[str, QIcon, FluentIconBase],
        title: str,
        content: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(icon, title, content, parent, detailed=True)
        self.url = url
        self.linkButton = HyperlinkButton(url, text, self)
        self.hBoxLayout.addWidget(self.linkButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(CARD["control_gap"])
