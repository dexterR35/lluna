"""Shared On/Off + selected-mode state machine for settings-backed model catalogs.

Enhance (Real-ESRGAN), Low-light (MIRNet), and Generate (FLUX/Qwen) each store
their enabled set and selected mode as a comma-separated settings string, with
the same parse/serialize/fallback rules. This factors that repeated ~50-line
block into one place, parameterized per catalog, so the three installer
modules only need to declare *what* their catalog is - not reimplement *how*
enabling and mode-selection works.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Iterable, List, Set, TypeVar

# Saved when every model in a catalog is Off (an empty string is read as
# "use factory defaults", so this sentinel distinguishes "explicitly none").
NONE_ENABLED = "__none__"

ModeT = TypeVar("ModeT")


@dataclass(frozen=True)
class EnabledModesCatalog(Generic[ModeT]):
    """Binds the shared state machine to one settings-backed model catalog."""

    mode_cls: type
    catalog_modes: Callable[[], List[ModeT]]
    default_enabled: tuple[str, ...]
    is_installed: Callable[[ModeT], bool]
    settings_section: str
    enabled_field: str = "enabled_models"
    mode_field: str = "mode"
    preferred_modes: tuple[ModeT, ...] = ()

    def _section(self):
        from backend.configuration.service import get_settings

        return getattr(get_settings(), self.settings_section)

    def get_enabled_setting(self) -> str:
        return getattr(self._section(), self.enabled_field)

    def set_enabled_setting(self, value: str) -> None:
        from backend.configuration.service import update_settings

        update_settings({self.settings_section: {self.enabled_field: value}})

    def get_mode_setting(self) -> str:
        return getattr(self._section(), self.mode_field)

    def set_mode_setting(self, value: str) -> None:
        from backend.configuration.service import update_settings

        update_settings({self.settings_section: {self.mode_field: value}})


def parse_enabled_values(catalog: EnabledModesCatalog, raw: str) -> Set[str]:
    """Missing/blank -> factory defaults; ``__none__`` -> all Off."""
    s = "" if raw is None else str(raw).strip()
    if not s:
        return set(catalog.default_enabled)
    if s == NONE_ENABLED:
        return set()
    values = {part.strip() for part in s.split(",") if part.strip()}
    valid = {m.value for m in catalog.mode_cls}
    return {v for v in values if v in valid}


def serialize_enabled_values(catalog: EnabledModesCatalog, values: Iterable[str]) -> str:
    ordered = []
    seen = set()
    for mode in catalog.catalog_modes():
        v = mode.value
        if v in values and v not in seen:
            ordered.append(v)
            seen.add(v)
    return ",".join(ordered) if ordered else NONE_ENABLED


def get_enabled_values(catalog: EnabledModesCatalog) -> Set[str]:
    return parse_enabled_values(catalog, catalog.get_enabled_setting())


def set_model_enabled(catalog: EnabledModesCatalog, mode: ModeT, enabled: bool) -> None:
    values = get_enabled_values(catalog)
    if enabled:
        values.add(mode.value)
    else:
        values.discard(mode.value)
    catalog.set_enabled_setting(serialize_enabled_values(catalog, values))


def selectable_modes(catalog: EnabledModesCatalog) -> List[ModeT]:
    """On + installed only (no phantom defaults - weights must be on disk)."""
    enabled = get_enabled_values(catalog)
    return [
        mode
        for mode in catalog.catalog_modes()
        if mode.value in enabled and catalog.is_installed(mode)
    ]


def ensure_selected_mode_valid(catalog: EnabledModesCatalog) -> ModeT:
    current = catalog.mode_cls(catalog.get_mode_setting())
    available = selectable_modes(catalog)
    if current in available:
        return current
    for preferred in catalog.preferred_modes:
        if preferred in available:
            catalog.set_mode_setting(preferred.value)
            return preferred
    if available:
        catalog.set_mode_setting(available[0].value)
        return available[0]
    return current
