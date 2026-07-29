from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.gui
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("qfluentwidgets")


def test_empty_model_selector_shows_install_action(qtbot) -> None:
    from ui.component.controls.inputs import (
        AppCombo,
        make_install_model_button,
        show_install_model_when_empty,
    )

    clicks: list[bool] = []
    combo = AppCombo()
    button = make_install_model_button(combo.parentWidget(), lambda: clicks.append(True))
    qtbot.addWidget(combo)
    qtbot.addWidget(button)

    show_install_model_when_empty(combo, button, has_models=False)
    assert combo.isHidden()
    assert not button.isHidden()

    button.click()
    assert clicks == [True]

    show_install_model_when_empty(combo, button, has_models=True)
    assert not combo.isHidden()
    assert button.isHidden()


def test_model_settings_route_reveals_requested_group(qtbot) -> None:
    import gui

    collapsed: list[bool] = []
    target = SimpleNamespace(setCollapsed=lambda value: collapsed.append(value))
    revealed: list[tuple[object, int, int]] = []
    settings = SimpleNamespace(
        generate_models_group=target,
        ensureWidgetVisible=lambda widget, x, y: revealed.append((widget, x, y)),
    )
    lazy_settings = SimpleNamespace(ensure_loaded=lambda: settings)
    switched: list[object] = []
    window = SimpleNamespace(
        advancedSettingInterface=lazy_settings,
        switchTo=lambda page: switched.append(page),
    )
    gui.SubtitleExtractorGUI._open_model_settings(window, "generate_models_group")
    qtbot.waitUntil(lambda: bool(revealed))

    assert switched == [lazy_settings]
    assert collapsed == [False]
    assert revealed == [(target, 0, 24)]
