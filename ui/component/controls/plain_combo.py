"""Back-compat - prefer ``ui.component.controls.inputs.AppCombo``."""

from ui.component.controls.inputs import AppCombo, PlainComboBox  # noqa: F401

__all__ = ["AppCombo", "PlainComboBox"]
