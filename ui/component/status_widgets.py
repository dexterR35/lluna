"""Reusable accessible job, error, and unavailable-state widgets."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from backend.application.jobs import JobStatus
from backend.diagnostics.errors import UserError


class JobProgressWidget(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Job progress")
        root = QVBoxLayout(self)
        self.phase_label = QLabel("Queued", self)
        self.phase_label.setAccessibleName("Current processing phase")
        root.addWidget(self.phase_label)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName("Overall progress")
        root.addWidget(self.progress)
        self.detail_label = QLabel("", self)
        self.detail_label.setWordWrap(True)
        self.detail_label.setAccessibleName("Processing details")
        root.addWidget(self.detail_label)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setAccessibleName("Cancel processing")
        self.cancel_button.clicked.connect(self.cancel_requested)
        actions.addWidget(self.cancel_button)
        root.addLayout(actions)

    def set_status(self, status: JobStatus) -> None:
        phase = status.phase.value.replace("_", " ").title()
        self.phase_label.setText(phase)
        self.progress.setValue(status.progress)
        bits = [
            value
            for value in (
                f"Model: {status.model}" if status.model else "",
                f"Device: {status.device}" if status.device else "",
                f"Output: {status.output_path}" if status.output_path else "",
                f"Elapsed: {status.elapsed_seconds:.1f}s",
                status.message,
            )
            if value
        ]
        self.detail_label.setText("\n".join(bits))
        self.cancel_button.setEnabled(not status.phase.terminal)


class ErrorPanel(QWidget):
    copy_diagnostics_requested = Signal(str)
    retry_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Processing error")
        root = QVBoxLayout(self)
        self.title = QLabel("", self)
        self.title.setAccessibleName("Error title")
        root.addWidget(self.title)
        self.explanation = QLabel("", self)
        self.explanation.setWordWrap(True)
        self.explanation.setAccessibleName("Error explanation")
        root.addWidget(self.explanation)
        self.actions = QLabel("", self)
        self.actions.setWordWrap(True)
        self.actions.setAccessibleName("Suggested actions")
        root.addWidget(self.actions)
        self.details_toggle = QToolButton(self)
        self.details_toggle.setText("Technical details")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setAccessibleName("Show technical error details")
        root.addWidget(self.details_toggle)
        self.details = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setVisible(False)
        self.details.setAccessibleName("Technical error details")
        root.addWidget(self.details)
        self.details_toggle.toggled.connect(self.details.setVisible)
        buttons = QHBoxLayout()
        self.retry = QPushButton("Retry", self)
        self.retry.clicked.connect(self.retry_requested)
        buttons.addWidget(self.retry)
        self.copy = QPushButton("Copy diagnostics", self)
        self.copy.clicked.connect(
            lambda: self.copy_diagnostics_requested.emit(self.details.toPlainText())
        )
        buttons.addWidget(self.copy)
        buttons.addStretch(1)
        root.addLayout(buttons)

    def set_error(self, error: UserError) -> None:
        self.title.setText(error.title)
        self.explanation.setText(error.explanation)
        self.actions.setText(
            "\n".join(f"• {action}" for action in error.actions)
        )
        self.details.setPlainText(error.technical_details)
        self.retry.setVisible(error.retryable)
        self.copy.setEnabled(bool(error.technical_details))


class EmptyState(QWidget):
    action_requested = Signal()

    def __init__(self, title: str, explanation: str, action: str = "", parent=None):
        super().__init__(parent)
        self.setAccessibleName(title)
        root = QVBoxLayout(self)
        title_label = QLabel(title, self)
        title_label.setAccessibleName("Status")
        root.addWidget(title_label)
        detail = QLabel(explanation, self)
        detail.setWordWrap(True)
        detail.setAccessibleName("Status explanation")
        root.addWidget(detail)
        self.action = QPushButton(action, self)
        self.action.setAccessibleName(action or "Resolve unavailable state")
        self.action.setVisible(bool(action))
        self.action.clicked.connect(self.action_requested)
        root.addWidget(self.action)
