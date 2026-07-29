"""Persistent bottom-right model download queue and session history."""

from __future__ import annotations

from PySide6 import QtCore
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.config import tr
from backend.tools.first_run_downloads import pending_label
from backend.tools.model_download_queue import DownloadJobSnapshot
from backend.tools.model_download_registry import PendingDownload
from ui.component.cards.model_install_helpers import (
    model_download_queue,
    register_queue_listener,
    unregister_queue_listener,
)
from ui.component.controls.button_styles import make_button, make_stop_button
from ui.theme import (
    BG,
    BORDER,
    CARD_RADIUS,
    ERROR,
    MUTED,
    PRIMARY,
    SUCCESS,
    TEXT,
    TEXT_SECONDARY,
)

_PANEL_WIDTH = 460
_ROW_HEIGHT = 104
_MAX_VISIBLE_ROWS = 5


def _job_name(job: DownloadJobSnapshot) -> str:
    return pending_label(PendingDownload(job.kind, job.key))


def _format_bytes(value: int | float) -> str:
    amount = max(0.0, float(value))
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for candidate in units:
        unit = candidate
        if amount < 1024.0 or candidate == units[-1]:
            break
        amount /= 1024.0
    precision = 0 if unit == "B" else 1
    return f"{amount:.{precision}f} {unit}"


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _metrics_text(job: DownloadJobSnapshot) -> str:
    dl = tr["Downloads"]
    if job.state == "queued":
        return dl.get("QueuePosition", "Queue position {}").format(
            max(1, job.position)
        )
    if job.state == "stopping":
        return dl.get(
            "StoppingDetail",
            "Stopping and removing partial data...",
        )

    parts: list[str] = []
    if job.downloaded_bytes is not None:
        downloaded = _format_bytes(job.downloaded_bytes)
        if job.total_bytes:
            parts.append(f"{downloaded} / {_format_bytes(job.total_bytes)}")
        else:
            parts.append(downloaded)
    elif job.progress is not None:
        parts.append(f"{job.progress}%")

    if job.bytes_per_second and job.state == "active":
        parts.append(f"{_format_bytes(job.bytes_per_second)}/s")
    if job.eta_seconds is not None and job.state == "active":
        parts.append(
            dl.get("TimeLeft", "{} left").format(
                _format_duration(job.eta_seconds)
            )
        )
    if job.elapsed_seconds > 0:
        parts.append(
            dl.get("Elapsed", "{} elapsed").format(
                _format_duration(job.elapsed_seconds)
            )
        )

    if job.state == "completed" and "100%" not in parts:
        parts.insert(0, "100%")
    if job.state == "failed" and job.error:
        parts.append(job.error)
    if job.state == "cancelled":
        parts.append(dl.get("StoppedDetail", "Stopped by user"))
    return " · ".join(parts) or job.detail


class _DownloadRow(QFrame):
    """One model job: name, lifecycle state, and progress."""

    def __init__(self, job: DownloadJobSnapshot, stop_callback, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ModelDownloadRow")
        self.setFixedHeight(_ROW_HEIGHT)
        self.setAccessibleName(f"{_job_name(job)} download")
        self._job_id = job.job_id
        self._stop_callback = stop_callback

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 7)
        root.setSpacing(4)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        self.name_label = QLabel(_job_name(job), self)
        self.name_label.setStyleSheet(
            f"color: {TEXT}; font-weight: 600; background: transparent; border: none;"
        )
        self.name_label.setToolTip(self.name_label.text())
        heading.addWidget(self.name_label, 1)

        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        heading.addWidget(self.status_label, 0)

        self.stop_button = make_stop_button(
            tr["Downloads"].get("Stop", "Stop"),
            self,
            size="small",
        )
        self.stop_button.setAccessibleName(f"Stop {_job_name(job)} download")
        self.stop_button.clicked.connect(
            lambda: self._stop_callback(self._job_id)
        )
        heading.addWidget(self.stop_button, 0)
        root.addLayout(heading)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(7)
        self.progress_bar.setAccessibleName(f"{_job_name(job)} progress")
        root.addWidget(self.progress_bar)

        self.metrics_label = QLabel("", self)
        self.metrics_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            "background: transparent; border: none;"
        )
        self.metrics_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.metrics_label)

        self.setStyleSheet(
            f"""
            QFrame#ModelDownloadRow {{
                background: {BG};
                border: 1px solid {BORDER};
                border-radius: {CARD_RADIUS}px;
            }}
            QProgressBar {{
                background: {MUTED};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {PRIMARY};
                border-radius: 3px;
            }}
            """
        )
        self.update_job(job)

    def update_job(self, job: DownloadJobSnapshot) -> None:
        self._job_id = job.job_id
        dl = tr["Downloads"]
        status = job.state
        color = TEXT_SECONDARY
        self.progress_bar.show()
        self.stop_button.setVisible(status in {"active", "queued", "stopping"})
        self.stop_button.setEnabled(status in {"active", "queued"})
        self.stop_button.setText(
            dl.get("Stopping", "Stopping...")
            if status == "stopping"
            else dl.get("Stop", "Stop")
        )

        if status == "stopping":
            text = dl.get("Stopping", "Stopping...")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(job.progress or 0)
        elif status == "active":
            if job.operation == "uninstall":
                text = dl.get("Removing", "Removing…")
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(job.progress or 0)
            elif job.progress is None:
                text = dl.get("Installing", "Installing…")
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(0)
            else:
                text = dl.get("InstallingPercent", "Installing · {}%").format(
                    job.progress
                )
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(job.progress)
                color = PRIMARY
        elif status == "queued":
            ahead = max(0, job.position)
            if ahead:
                text = dl.get("QueuedAhead", "Queued · {} ahead").format(ahead)
            else:
                text = dl.get("Queued", "Queued")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        elif status == "completed":
            text = (
                dl.get("Removed", "Removed")
                if job.operation == "uninstall"
                else dl.get("Installed", "Installed")
            )
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            color = SUCCESS
        elif status == "cancelled":
            text = dl.get("Stopped", "Stopped")
            self.progress_bar.hide()
        else:
            text = dl.get("Failed", "Failed")
            self.progress_bar.hide()
            color = ERROR

        self.status_label.setText(text)
        self.metrics_label.setText(_metrics_text(job))
        self.metrics_label.setToolTip(job.error or job.detail or "")
        self.status_label.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )
        self.setToolTip(job.error or job.detail or "")


class ModelDownloadPanel(QFrame):
    """Floating queue panel that remains visible until finished jobs are cleared."""

    layout_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ModelDownloadPanel")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground)
        self.setAccessibleName("Model downloads")
        self.setFixedWidth(_PANEL_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(1)
        self.title_label = QLabel(tr["Downloads"].get("Title", "Downloads"), self)
        self.title_label.setStyleSheet(
            f"color: {TEXT}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        titles.addWidget(self.title_label)
        subtitle = QLabel(
            tr["Downloads"].get("OneAtATime", "Models install one at a time"),
            self,
        )
        subtitle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            "background: transparent; border: none;"
        )
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.clear_button = make_button(
            tr["Downloads"].get("Clear", "Clear"),
            "secondary",
            self,
            size="small",
        )
        self.clear_button.clicked.connect(
            model_download_queue().clear_finished
        )
        header.addWidget(self.clear_button)
        root.addLayout(header)

        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content = QWidget(self.scroll)
        self.content.setStyleSheet("background: transparent;")
        self.rows_layout = QVBoxLayout(self.content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll)

        self.setStyleSheet(
            f"""
            QFrame#ModelDownloadPanel {{
                background: {MUTED};
                border: 1px solid {BORDER};
                border-radius: {CARD_RADIUS + 2}px;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            """
        )

        register_queue_listener(self.refresh)
        self.destroyed.connect(
            lambda: unregister_queue_listener(self.refresh)
        )
        self.elapsed_timer = QtCore.QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.refresh)
        self.refresh()

    def _stop_job(self, job_id: int) -> None:
        model_download_queue().stop_job(job_id)

    def refresh(self) -> None:
        jobs = model_download_queue().jobs()
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for job in jobs:
            self.rows_layout.addWidget(
                _DownloadRow(job, self._stop_job, self.content)
            )
        self.rows_layout.addStretch(1)

        pending = sum(
            job.state in {"active", "queued", "stopping"} for job in jobs
        )
        title = tr["Downloads"].get("Title", "Downloads")
        self.title_label.setText(f"{title} ({pending})" if pending else title)
        self.clear_button.setVisible(
            any(
                job.state not in {"active", "queued", "stopping"}
                for job in jobs
            )
        )

        rows = min(max(len(jobs), 1), _MAX_VISIBLE_ROWS)
        self.scroll.setFixedHeight(rows * _ROW_HEIGHT + max(0, rows - 1) * 6)
        self.adjustSize()
        self.setVisible(bool(jobs))
        has_running = any(
            job.state in {"active", "stopping"} for job in jobs
        )
        if has_running and not self.elapsed_timer.isActive():
            self.elapsed_timer.start()
        elif not has_running and self.elapsed_timer.isActive():
            self.elapsed_timer.stop()
        if jobs:
            self.raise_()
        self.layout_changed.emit()
