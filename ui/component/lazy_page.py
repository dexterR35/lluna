"""Small routed placeholder that constructs a feature only on first visit."""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtWidgets


class LazyPage(QtWidgets.QWidget):
    loaded = QtCore.Signal(QtWidgets.QWidget)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        object_name: str,
        factory: Callable[[], QtWidgets.QWidget],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAccessibleName(object_name)
        self._factory = factory
        self._content: QtWidgets.QWidget | None = None
        self._loading = False
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(24, 24, 24, 24)
        self._status = QtWidgets.QLabel("Open this page to load the feature.", self)
        self._status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._status.setAccessibleName("Feature loading status")
        self._layout.addWidget(self._status)

    @property
    def content(self) -> QtWidgets.QWidget | None:
        return self._content

    def ensure_loaded(self) -> QtWidgets.QWidget | None:
        if self._content is not None or self._loading:
            return self._content
        self._loading = True
        self._status.setText("Loading feature…")
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        try:
            content = self._factory()
            self._layout.removeWidget(self._status)
            self._status.deleteLater()
            self._content = content
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.addWidget(content)
            self.loaded.emit(content)
            return content
        except Exception as exc:
            self._status.setText(
                "This feature could not be loaded.\n"
                f"Technical detail: {type(exc).__name__}"
            )
            self.failed.emit(type(exc).__name__)
            return None
        finally:
            self._loading = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._content is None and not self._loading:
            QtCore.QTimer.singleShot(0, self.ensure_loaded)
