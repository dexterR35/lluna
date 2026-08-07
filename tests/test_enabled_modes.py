from __future__ import annotations

from backend.configuration.service import update_settings
from backend.tools.installers import enhance as enhance_models
from backend.tools.shared.constants import EnhanceMode


def test_default_enabled_matches_catalog_defaults() -> None:
    assert enhance_models.get_enabled_values() == {EnhanceMode.X2PLUS.value}


def test_set_model_enabled_round_trips_through_settings() -> None:
    enhance_models.set_model_enabled(EnhanceMode.X4PLUS, True)
    assert enhance_models.get_enabled_values() == {
        EnhanceMode.X2PLUS.value,
        EnhanceMode.X4PLUS.value,
    }
    enhance_models.set_model_enabled(EnhanceMode.X2PLUS, False)
    assert enhance_models.get_enabled_values() == {EnhanceMode.X4PLUS.value}


def test_none_enabled_sentinel_round_trips_to_empty_set() -> None:
    assert enhance_models.serialize_enabled_values(set()) == "__none__"
    assert enhance_models.parse_enabled_values("__none__") == set()


def test_selectable_modes_requires_enabled_and_installed(monkeypatch) -> None:
    monkeypatch.setattr(
        enhance_models, "is_model_installed", lambda mode: mode == EnhanceMode.X4PLUS
    )
    enhance_models.set_model_enabled(EnhanceMode.X2PLUS, True)
    enhance_models.set_model_enabled(EnhanceMode.X4PLUS, True)
    # X2PLUS is enabled but not "installed" per the monkeypatch, so only
    # X4PLUS should be selectable.
    assert enhance_models.selectable_modes() == [EnhanceMode.X4PLUS]


def test_ensure_selected_mode_valid_falls_back_to_preferred(monkeypatch) -> None:
    monkeypatch.setattr(enhance_models, "is_model_installed", lambda mode: True)
    enhance_models.set_model_enabled(EnhanceMode.X2PLUS, True)
    enhance_models.set_model_enabled(EnhanceMode.X4PLUS, True)

    # X4PLUS is currently selected but disabled below, so the resolver must
    # fall back to its preferred mode (X2PLUS) rather than an arbitrary one.
    update_settings({"enhancement": {"mode": EnhanceMode.X4PLUS.value}})
    enhance_models.set_model_enabled(EnhanceMode.X4PLUS, False)
    assert enhance_models.ensure_selected_mode_valid() == EnhanceMode.X2PLUS


def test_ensure_selected_mode_valid_returns_current_when_nothing_available(
    monkeypatch,
) -> None:
    monkeypatch.setattr(enhance_models, "is_model_installed", lambda mode: False)
    enhance_models.set_model_enabled(EnhanceMode.X2PLUS, False)
    enhance_models.set_model_enabled(EnhanceMode.X4PLUS, False)
    update_settings({"enhancement": {"mode": EnhanceMode.X2PLUS.value}})
    assert enhance_models.ensure_selected_mode_valid() == EnhanceMode.X2PLUS
