from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.gui
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("qfluentwidgets")


def test_prompt_controls_fit_in_compact_width(qtbot) -> None:
    from ui.dashboard_interface import _PromptBox
    from ui.theme import BUTTON_SIZES

    prompt = _PromptBox()
    qtbot.addWidget(prompt)
    prompt.resize(480, prompt.sizeHint().height())
    prompt.show()
    qtbot.wait(10)

    controls = [
        control
        for control in (
            prompt.model_combo,
            prompt.install_model_btn,
            prompt.size_combo,
        )
        if control.isVisible()
    ]
    assert len(controls) == 2
    assert prompt.width() == 480
    assert all(control.geometry().right() < prompt.width() for control in controls)
    for left, right in zip(controls, controls[1:], strict=False):
        assert left.geometry().right() < right.geometry().left()
    assert prompt.size_combo.currentText().startswith("Size: ")
    assert prompt.steps_combo is None

    small_height = BUTTON_SIZES["small"]["height"]
    assert prompt.attach_btn.height() == small_height
    assert prompt.generate_btn.height() == small_height


def test_upload_panel_hides_secondary_format_copy(qtbot) -> None:
    from ui.component.preview.upload_drop_panel import UploadDropPanel

    panel = UploadDropPanel("Supported formats: PNG, JPG")
    qtbot.addWidget(panel)
    panel.show()

    assert panel._formats.isHidden()
    assert panel.toolTip() == "Supported formats: PNG, JPG"
