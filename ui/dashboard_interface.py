"""ChatGPT-style home dashboard: greeting, PC info, prompt shortcuts."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    PlainTextEdit,
    SubtitleLabel,
    TitleLabel,
)

from backend.config import tr
from backend.tools.system_info import collect_system_info, greeting_for_now
from ui.component.cards.info_setting_card import InfoSettingCard
from ui.component.cards.setting_card_style import apply_content_column_width
from ui.component.controls.button_styles import make_button
from ui.theme import HOME, PAGE, PRIMARY, apply_page_bg

# Content column stretch from SETTINGS content_ratio (~80% → 1:8:1)
_COLUMN_STRETCH = 8
_SIDE_STRETCH = 1


class _PromptBox(QWidget):
    submitted = Signal(str)
    attach_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input = None
        self.setObjectName("PromptBox")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(HOME["gap"])

        hd = tr["HomeDashboard"]
        self.input = PlainTextEdit(self)
        self.input.setPlaceholderText(hd["PromptPlaceholder"])
        self.input.setFixedHeight(HOME["prompt_h"])
        self.input.setTabChangesFocus(True)
        self.input.installEventFilter(self)
        root.addWidget(self.input)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(HOME["gap"])

        self.attach_btn = make_button(hd["Attach"], "secondary", self, FluentIcon.FOLDER)
        self.attach_btn.clicked.connect(self.attach_clicked.emit)
        row.addWidget(self.attach_btn)
        row.addStretch(1)
        root.addLayout(row)

    def _submit(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)
        self.input.clear()

    def eventFilter(self, obj, event):
        inp = getattr(self, "input", None)
        if inp is not None and obj is inp and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False
                self._submit()
                return True
        return super().eventFilter(obj, event)


class DashboardInterface(QWidget):
    """Landing home — greeting, system SettingCards, prompt."""

    open_bg_remove = Signal()
    open_video = Signal()
    open_settings = Signal()
    open_files = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("DashboardInterface")
        self._info = collect_system_info()
        self._build()

    def _build(self):
        hd = tr["HomeDashboard"]
        scroll = QScrollArea(self)
        scroll.setObjectName("DashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        page = QWidget()
        page.setObjectName("DashboardPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(
            HOME["pad_x"],
            HOME["pad_top"],
            HOME["pad_x"],
            HOME["pad_bottom"],
        )
        outer.setSpacing(0)

        self._column = QWidget(page)
        self._column.setObjectName("DashboardColumn")
        self._column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col = QVBoxLayout(self._column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        column = self._column

        period = greeting_for_now()
        greet_key = {
            "morning": "GreetingMorning",
            "afternoon": "GreetingAfternoon",
            "evening": "GreetingEvening",
        }[period]
        greet = TitleLabel(hd[greet_key].format(self._info.username), column)
        greet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(greet)

        sub_row = QHBoxLayout()
        sub_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_row.setSpacing(HOME["sub_gap"])
        sub_a = SubtitleLabel(hd["SubtitleLead"], column)
        sub_b = SubtitleLabel(hd["SubtitleAccent"], column)
        try:
            sub_b.setTextColor(PRIMARY, PRIMARY)
        except Exception:
            sub_b.setStyleSheet(f"color: {PRIMARY};")
        sub_row.addWidget(sub_a)
        sub_row.addWidget(sub_b)
        col.addSpacing(HOME["after_greet"])
        col.addLayout(sub_row)

        col.addSpacing(HOME["section_gap"])
        col.addWidget(SubtitleLabel(hd["PcInfoSection"], column))
        col.addSpacing(HOME["section_title_gap"])

        chips_host = QWidget(column)
        chips_row = QHBoxLayout(chips_host)
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(HOME["gap"])
        for icon, title, value in (
            (FluentIcon.INFO, hd["ChipOs"], self._info.os_name),
            (FluentIcon.DEVELOPER_TOOLS, hd["ChipCpu"], self._info.cpu),
            (FluentIcon.LIBRARY, hd["ChipRam"], self._info.ram),
            (FluentIcon.PHOTO, hd["ChipGpu"], self._info.gpu),
            (FluentIcon.SPEED_HIGH, hd["ChipAccel"], self._info.accelerator),
        ):
            card = InfoSettingCard(icon, title, value, chips_host)
            chips_row.addWidget(card, 1)
        col.addWidget(chips_host)

        col.addSpacing(HOME["prompt_gap"])
        self.prompt = _PromptBox(column)
        self.prompt.submitted.connect(self._on_prompt)
        self.prompt.attach_clicked.connect(self.open_files.emit)
        col.addWidget(self.prompt)

        hint = BodyLabel(hd["PromptHint"], column)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        col.addSpacing(HOME["hint_gap"])
        col.addWidget(hint)

        outer.addStretch(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(_SIDE_STRETCH)
        row.addWidget(column, _COLUMN_STRETCH)
        row.addStretch(_SIDE_STRETCH)
        outer.addLayout(row)
        outer.addStretch(2)

        scroll.setWidget(page)
        self._scroll = scroll
        self._page = page
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        self.apply_theme_bg()

    def apply_theme_bg(self):
        """Scroll + inner page default to white — paint both with ``PAGE['bg']``."""
        apply_page_bg(self, self._scroll, self._page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        apply_content_column_width(
            self._column,
            self._scroll.viewport().width() - HOME["pad_x"] * 2,
        )

    def _on_prompt(self, text: str):
        """Route natural-language shortcuts to tools."""
        q = text.lower()
        if any(k in q for k in ("setting", "config", "theme", "model")):
            self.open_settings.emit()
        elif any(k in q for k in ("subtitle", "watermark", "video", "inpaint", "sttn", "lama")):
            self.open_video.emit()
        elif any(k in q for k in ("background", "bg", "cutout", "remove bg", "rembg")):
            self.open_bg_remove.emit()
        elif any(k in q for k in ("open", "file", "image", "upload", "attach")):
            self.open_files.emit()
        else:
            self.open_bg_remove.emit()
