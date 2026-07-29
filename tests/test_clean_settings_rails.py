from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.gui
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("qfluentwidgets")


def test_upscale_rail_has_controls_without_helper_text(qtbot) -> None:
    from ui.upscale_interface import UpscaleInterface

    page = UpscaleInterface()
    qtbot.addWidget(page)

    assert not hasattr(page, "recommendation_label")
    assert not hasattr(page, "denoise_hint")
    assert page.denoise_switch.toolTip()


def test_remove_bg_rail_has_no_protect_status_sentence(qtbot) -> None:
    from ui.bg_remove_interface import BgRemoveInterface

    page = BgRemoveInterface()
    qtbot.addWidget(page)

    assert not hasattr(page, "protect_status")
