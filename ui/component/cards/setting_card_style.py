"""Shared Midgard card chrome — colors + density from ``ui.theme.CARD``."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QWidget

from ui.theme import CARD, SETTINGS, card_qss

__all__ = [
    "compact_setting_card",
    "apply_settings_card",
    "settings_content_summary",
    "apply_content_column_width",
    "apply_card_chrome",
]


def apply_card_chrome(card: QWidget) -> None:
    """Paint card from ``theme.card_qss`` (Midgard QFrame — no Fluent sheet API)."""
    # Leftover Fluent SettingCard subclasses still paint their own fill
    if type(card).paintEvent is not QFrame.paintEvent:
        card.paintEvent = lambda e, _c=card: QFrame.paintEvent(_c, e)  # type: ignore[method-assign]

    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setStyleSheet(card_qss())


def settings_content_summary(text: str, *, max_len: int = 90) -> str:
    """First line only — full text stays in tooltip."""
    line = (text or "").split("\n", 1)[0].strip()
    if len(line) > max_len:
        line = line[: max_len - 1].rstrip() + "…"
    return line


def _apply_card_text(card: QWidget, *, content_max_h: int, word_wrap: bool) -> None:
    c = CARD
    if hasattr(card, "titleLabel"):
        card.titleLabel.setWordWrap(False)
        title_font = QFont(card.titleLabel.font())
        title_font.setPointSize(c["title_size"])
        title_font.setWeight(QFont.Weight.DemiBold)
        card.titleLabel.setFont(title_font)
        card.titleLabel.setStyleSheet(
            f"color: {c['title']}; background: transparent; border: none;"
        )

    if hasattr(card, "contentLabel"):
        card.contentLabel.setWordWrap(word_wrap)
        card.contentLabel.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        card.contentLabel.setMaximumHeight(content_max_h)
        content_font = QFont(card.contentLabel.font())
        content_font.setPointSize(c["content_size"])
        card.contentLabel.setFont(content_font)
        card.contentLabel.setStyleSheet(
            f"color: {c['content']}; background: transparent; border: none;"
        )


def compact_setting_card(card: QWidget) -> QWidget:
    """Apply theme CARD layout + Midgard chrome (bg / border / title / content)."""
    c = CARD
    apply_card_chrome(card)

    card.setFixedHeight(c["height"])
    if hasattr(card, "hBoxLayout"):
        card.hBoxLayout.setContentsMargins(c["pad_x_left"], 0, c["pad_x_right"], 0)
    try:
        card.iconLabel.setFixedSize(c["icon"], c["icon"])
    except Exception:
        pass

    if hasattr(card, "vBoxLayout"):
        card.vBoxLayout.setSpacing(c["spacing"])
        card.vBoxLayout.setContentsMargins(0, c["pad_y"], 0, c["pad_y"])
        card.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    if hasattr(card, "hBoxLayout"):
        card.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    _apply_card_text(card, content_max_h=c["content_max_h"], word_wrap=True)

    return card


def apply_settings_card(card: QWidget) -> QWidget:
    """Compact settings row — one-line summary; hover for full help."""
    c = CARD
    s = SETTINGS
    apply_card_chrome(card)

    card.setFixedHeight(s["card_height"])
    if hasattr(card, "hBoxLayout"):
        card.hBoxLayout.setContentsMargins(c["pad_x_left"], 0, c["pad_x_right"], 0)
        card.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    try:
        card.iconLabel.setFixedSize(c["icon"], c["icon"])
    except Exception:
        pass

    if hasattr(card, "vBoxLayout"):
        card.vBoxLayout.setSpacing(1)
        card.vBoxLayout.setContentsMargins(0, 4, 0, 4)
        card.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    _apply_card_text(card, content_max_h=s["card_content_max_h"], word_wrap=False)

    return card


def apply_content_column_width(column, available_width: int, *, ratio: float | None = None) -> None:
    """Keep settings / home content at ``PAGE`` content ratio (not full bleed)."""
    if available_width <= 0:
        return
    r = SETTINGS["content_ratio"] if ratio is None else ratio
    min_w = SETTINGS["content_min_w"]
    target = max(min_w, int(available_width * r))
    column.setMaximumWidth(target)
    column.setMinimumWidth(min(target, min_w))
