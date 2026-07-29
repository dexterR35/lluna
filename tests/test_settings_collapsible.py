from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.gui
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("qfluentwidgets")


def test_settings_group_is_collapsed_by_default_and_title_toggles(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    from ui.component.cards.midgard_setting_cards import MidgardCardGroup

    group = MidgardCardGroup("Generate Models")
    group.addSettingCard(QLabel("FLUX", group))
    qtbot.addWidget(group)
    group.show()

    assert group.isCollapsed()
    assert group.cardHost.isHidden()
    assert not group.titleButton.isChecked()

    qtbot.mouseClick(group.titleButton, Qt.MouseButton.LeftButton)

    assert not group.isCollapsed()
    assert not group.cardHost.isHidden()
    assert group.titleButton.isChecked()

    group.titleButton.click()
    assert group.isCollapsed()
    assert group.cardHost.isHidden()


def test_reset_is_inside_expanded_content(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    from ui.component.cards.midgard_setting_cards import MidgardCardGroup

    group = MidgardCardGroup("Processing", resettable=True)
    group.addSettingCard(QLabel("Frames", group))
    qtbot.addWidget(group)
    group.show()

    assert group.resetButton is not None
    assert group.resetButton.parentWidget().parentWidget() is group.cardHost
    assert not group.resetButton.isVisible()

    group.setCollapsed(False)
    assert group.resetButton.isVisible()


def test_non_slider_group_has_no_reset_action(qtbot) -> None:
    from ui.component.cards.midgard_setting_cards import MidgardCardGroup

    group = MidgardCardGroup("Generate Models")
    qtbot.addWidget(group)
    assert group.resetButton is None
