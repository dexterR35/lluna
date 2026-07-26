"""Compact RAM / GPU / CPU readout for the side nav (below Settings)."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from backend.tools.system_info import format_bytes_short, sample_app_resources
from ui.theme import NAV, TEXT_SECONDARY


class NavResourceMeter(QtWidgets.QWidget):
    """Small secondary-text meter: app RAM, GPU VRAM, and CPU % on one line."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("NavResourceMeter")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(
            NAV["meter_pad_x"],
            NAV["meter_pad_y"],
            NAV["meter_pad_x"],
            NAV["meter_pad_y"],
        )
        root.setSpacing(0)

        self.label = QtWidgets.QLabel("RAM — · GPU — · CPU —", self)
        self.label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; background: transparent; "
            f"font-size: {NAV['meter_font']}px;"
        )
        self.label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.label.setWordWrap(True)
        root.addWidget(self.label, 1)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(NAV["meter_interval_ms"])
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def set_compact(self, compact: bool) -> None:
        """Hide text when the nav rail is icon-only."""
        self.setVisible(not compact)

    @QtCore.Slot()
    def refresh(self) -> None:
        sample = sample_app_resources()
        ram = format_bytes_short(sample.ram_mb)
        if sample.gpu_used_mb is not None and sample.gpu_total_mb is not None:
            gpu = (
                f"{format_bytes_short(sample.gpu_used_mb)}/"
                f"{format_bytes_short(sample.gpu_total_mb)}"
            )
        else:
            gpu = "—"
        cpu = f"{sample.cpu_percent:.0f}%" if sample.cpu_percent is not None else "—"
        self.label.setText(f"RAM {ram} · GPU {gpu} · CPU {cpu}")
