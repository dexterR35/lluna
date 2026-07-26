"""Narrow Yes/No confirm dialog (Fluent MessageBox sized from theme)."""

from __future__ import annotations

from qfluentwidgets import MessageBox
from qfluentwidgets.common.auto_wrap import TextWrap

from backend.config import tr
from ui.theme import DIALOG


def confirm_dialog(title: str, content: str, parent=None) -> MessageBox:
    """Build a compact Yes/No MessageBox (does not exec)."""
    d = DIALOG
    width = int(d["confirm_w"])
    box = MessageBox(title, content, parent)

    yes = tr["Common"].get("Yes", "Yes") if tr.has_section("Common") else "Yes"
    no = tr["Common"].get("No", "No") if tr.has_section("Common") else "No"
    box.yesButton.setText(yes)
    box.cancelButton.setText(no)

    # Fluent wraps using the full window width - re-wrap for our narrow card
    chars = max(
        min(int(width / d["confirm_wrap_div"]), d["confirm_wrap_max"]),
        d["confirm_wrap_min"],
    )
    box.contentLabel.setText(TextWrap.wrap(content, chars, False)[0])
    box.contentLabel.adjustSize()
    box.titleLabel.adjustSize()

    box.buttonGroup.setMinimumWidth(width)
    box.widget.setFixedSize(
        width,
        box.contentLabel.y() + box.contentLabel.height() + d["confirm_extra_h"],
    )
    return box


def ask_confirm(title: str, content: str, parent=None) -> bool:
    """Show Yes/No confirm; True if Yes."""
    return bool(confirm_dialog(title, content, parent).exec())
