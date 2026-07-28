from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.gui
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("qfluentwidgets")


def test_qapplication_creation_is_repeatable() -> None:
    import gui

    first = gui.create_application(["midgard-test"])
    second = gui.create_application(["midgard-test-again"])
    assert first is second


def test_shared_status_widgets_have_accessible_names() -> None:
    from ui.component.status_widgets import EmptyState, ErrorPanel, JobProgressWidget

    progress = JobProgressWidget()
    error = ErrorPanel()
    empty = EmptyState("No model installed", "Install a model to continue.", "Models")
    assert progress.accessibleName()
    assert progress.cancel_button.accessibleName()
    assert error.accessibleName()
    assert empty.accessibleName()
