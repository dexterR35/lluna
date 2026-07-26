"""Reusable Midgard inputs - Fluent ComboBox + labeled fields (Fluent chrome).

Use in SectionCard settings rails::

    field = make_section_combo(
        parent,
        label="Model",
        fetch=selectable_modes,
        label_of=lambda m: tr["BgRemoveMode"].get(m.name, m.name),
        data_of=lambda m: m.value,
        current=config.bgRemoveMode.value,
        on_change=...,
    )
    layout.addWidget(field)
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, qconfig
from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu
from qfluentwidgets.components.widgets.menu import MenuAnimationType

from backend.config import tr
from ui.theme import FORM

# (label, userData)
ComboItem = Tuple[str, Any]
FetchItems = Callable[[], Iterable[Any]]
LabelOf = Callable[[Any], str]
DataOf = Callable[[Any], Any]


class _NoAniComboMenu(ComboBoxMenu):
    """Dropdown without Fluent slide/fade animation."""

    def exec(self, pos, ani=True, aniType=MenuAnimationType.DROP_DOWN):
        return super().exec(pos, ani=False, aniType=MenuAnimationType.NONE)


class AppCombo(ComboBox):
    """Fluent dropdown - no popup animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaxVisibleItems(FORM["combo_max_visible"])

    def _createComboMenu(self):
        return _NoAniComboMenu(self)


# Back-compat name used across the app
PlainComboBox = AppCombo


class LabeledField(QWidget):
    """Label above a control - SectionCard settings field layout."""

    def __init__(
        self,
        label: str,
        control: QWidget,
        parent=None,
        *,
        tooltip: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setObjectName("LabeledField")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(FORM["field_spacing"])

        self.label = BodyLabel(label, self)
        root.addWidget(self.label)

        self.control = control
        if tooltip:
            control.setToolTip(tooltip)
        root.addWidget(control)


def fill_combo(
    combo: ComboBox,
    items: Sequence[ComboItem],
    *,
    current: Any = None,
    match: Optional[Callable[[Any, Any], bool]] = None,
) -> int:
    """Replace combo items with ``(label, data)`` pairs; select ``current``."""
    equals = match or (lambda a, b: a == b)
    combo.blockSignals(True)
    combo.clear()
    select = 0
    for i, (label, data) in enumerate(items):
        combo.addItem(label, userData=data)
        if current is not None and equals(data, current):
            select = i
    if items:
        combo.setCurrentIndex(select)
    combo.blockSignals(False)
    return select


def fetch_combo_items(
    fetch: FetchItems,
    *,
    label_of: LabelOf,
    data_of: Optional[DataOf] = None,
) -> list[ComboItem]:
    """Run ``fetch()`` and map rows to ``(label, data)``."""
    to_data = data_of or (lambda x: x)
    return [(label_of(row), to_data(row)) for row in fetch()]


def refresh_combo(
    combo: ComboBox,
    fetch: FetchItems,
    *,
    label_of: LabelOf,
    data_of: Optional[DataOf] = None,
    current: Any = None,
    match: Optional[Callable[[Any, Any], bool]] = None,
) -> int:
    """Fetch dropdown data and refill the combo."""
    items = fetch_combo_items(fetch, label_of=label_of, data_of=data_of)
    return fill_combo(combo, items, current=current, match=match)


def enum_option_texts(section: str, options) -> list[str]:
    """Map config enum options to translation labels by enum name."""
    return [tr[section].get(opt.name, opt.name) for opt in options]


def bind_config_enum_combo(
    combo: ComboBox,
    config_item,
    section: str,
) -> None:
    """Fetch enum options from config, fill combo, keep qconfig in sync."""
    options = list(config_item.validator.options)
    texts = enum_option_texts(section, options)
    items = list(zip(texts, options))
    current = qconfig.get(config_item)
    fill_combo(combo, items, current=current)

    def _on_index(index: int, item=config_item, box=combo):
        data = box.itemData(index)
        if data is not None:
            qconfig.set(item, data)

    combo.currentIndexChanged.connect(_on_index)

    def _sync(value, box=combo):
        idx = box.findData(value)
        if idx < 0 or box.currentIndex() == idx:
            return
        box.blockSignals(True)
        box.setCurrentIndex(idx)
        box.blockSignals(False)

    config_item.valueChanged.connect(_sync)


def make_section_combo(
    parent: QWidget,
    *,
    label: str,
    fetch: FetchItems,
    label_of: LabelOf,
    data_of: Optional[DataOf] = None,
    current: Any = None,
    tooltip: Optional[str] = None,
    on_change: Optional[Callable[[Any], None]] = None,
    match: Optional[Callable[[Any, Any], bool]] = None,
) -> LabeledField:
    """SectionCard field: label + Fluent ComboBox filled from ``fetch()``."""
    combo = AppCombo(parent)
    field = LabeledField(label, combo, parent, tooltip=tooltip)
    refresh_combo(
        combo,
        fetch,
        label_of=label_of,
        data_of=data_of,
        current=current,
        match=match,
    )
    if on_change is not None:

        def _emit(index: int, box=combo, cb=on_change):
            if index < 0:
                return
            data = box.itemData(index)
            if data is not None:
                cb(data)

        combo.currentIndexChanged.connect(_emit)
    return field
