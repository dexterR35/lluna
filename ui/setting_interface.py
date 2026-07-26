"""Video workspace settings — label above control in SectionCard."""

from __future__ import annotations

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from qfluentwidgets import StrongBodyLabel, SwitchButton, qconfig

from backend.config import config, tr, HARDWARE_ACCELERATION_OPTION
from ui.component.controls.inputs import AppCombo, LabeledField, bind_config_enum_combo
from ui.theme import FORM


class SettingInterface(QtWidgets.QVBoxLayout):

    def __init__(self, parent):
        super().__init__()
        self._parent = parent
        # Margins come from WorkspacePage SectionCard
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(FORM["field_spacing"])

        # Inpainting model — fetch enum options from config
        self.inpaint_mode_combo = AppCombo(parent)
        inpaint_field = LabeledField(
            tr["SubtitleExtractorGUI"]["InpaintMode"],
            self.inpaint_mode_combo,
            parent,
            tooltip=tr["SubtitleExtractorGUI"]["InpaintModeDesc"],
        )
        bind_config_enum_combo(
            self.inpaint_mode_combo, config.inpaintMode, "InpaintMode"
        )
        self.addWidget(inpaint_field)

        # Subtitle detection
        self.subtitle_detect_model_combo = AppCombo(parent)
        detect_field = LabeledField(
            tr["SubtitleExtractorGUI"]["SubtitleDetectMode"],
            self.subtitle_detect_model_combo,
            parent,
            tooltip=tr["SubtitleExtractorGUI"]["SubtitleDetectModeDesc"],
        )
        bind_config_enum_combo(
            self.subtitle_detect_model_combo,
            config.subtitleDetectMode,
            "SubtitleDetectMode",
        )
        self.addWidget(detect_field)

        # Hardware acceleration
        self.addWidget(StrongBodyLabel(tr["Setting"]["HardwareAcceleration"], parent))
        self.hardware_acceleration = SwitchButton(parent)
        self.hardware_acceleration.setOnText(tr["BgRemove"].get("ToggleOn", "On"))
        self.hardware_acceleration.setOffText(tr["BgRemove"].get("ToggleOff", "Off"))
        self.hardware_acceleration.setToolTip(tr["Setting"]["HardwareAccelerationDesc"])
        self.hardware_acceleration.setChecked(bool(qconfig.get(config.hardwareAcceleration)))
        self.hardware_acceleration.checkedChanged.connect(self._on_hw_accel_changed)
        if not HARDWARE_ACCELERATION_OPTION:
            self.hardware_acceleration.setChecked(False)
            self.hardware_acceleration.setEnabled(False)
            self.hardware_acceleration.setToolTip(tr["Setting"]["HardwareAccelerationNO"])
            config.set(config.hardwareAcceleration, False)
        hw_row = QtWidgets.QHBoxLayout()
        hw_row.setContentsMargins(0, 0, 0, 0)
        hw_row.addWidget(self.hardware_acceleration, 0, Qt.AlignmentFlag.AlignLeft)
        hw_row.addStretch(1)
        self.addLayout(hw_row)

        self.addStretch(1)

    def _on_hw_accel_changed(self, checked: bool):
        qconfig.set(config.hardwareAcceleration, bool(checked))

    def set_inpaint_mode_enabled(self, enabled):
        """Enable or disable the inpaint mode combo box."""
        self.inpaint_mode_combo.setEnabled(enabled)

    def reset_setting(self):
        """Reset all settings to defaults."""
        pass
