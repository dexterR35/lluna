from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from backend.configuration.loader import ConfigurationLoader
from backend.configuration.models import ApplicationConfiguration, SubtitleSettings
from backend.diagnostics.errors import ConfigurationError


def test_configuration_precedence_and_legacy_migration(tmp_path) -> None:
    shipped = tmp_path / "shipped.json"
    legacy = tmp_path / "legacy.json"
    user = tmp_path / "user.json"
    shipped.write_text(
        json.dumps({"subtitle": {"sttn_max_load_num": 20}}),
        encoding="utf-8",
    )
    legacy.write_text(
        json.dumps({"Sttn": {"MaxLoadNum": 30}}),
        encoding="utf-8",
    )

    loaded = ConfigurationLoader().load(
        shipped_file=shipped,
        user_file=user,
        legacy_file=legacy,
        environ={"LLUNA_INPAINT_MODE": "lama"},
        overrides={"subtitle": {"sttn_max_load_num": 40}},
    )

    assert loaded.value.subtitle.inpaint_mode == "lama"
    assert loaded.value.subtitle.sttn_max_load_num == 40
    assert loaded.provenance == (
        "compiled defaults",
        f"shipped:{shipped}",
        f"legacy:{legacy}",
        "environment",
        "runtime overrides",
    )


def test_corrupt_user_configuration_is_backed_up(tmp_path) -> None:
    user = tmp_path / "runtime.json"
    user.write_text("{broken", encoding="utf-8")

    loaded = ConfigurationLoader().load(
        shipped_file=tmp_path / "missing-defaults.json",
        user_file=user,
        legacy_file=tmp_path / "missing-legacy.json",
        environ={},
    )

    assert loaded.value == ApplicationConfiguration()
    assert not user.exists()
    assert len(loaded.recovered_files) == 1
    assert loaded.recovered_files[0].is_file()
    assert loaded.warnings


def test_configuration_save_is_atomic_and_round_trips(tmp_path) -> None:
    path = tmp_path / "runtime.json"
    loader = ConfigurationLoader()
    expected = ApplicationConfiguration(subtitle=SubtitleSettings(inpaint_mode="opencv"))

    loader.save(expected, path=path)
    loaded = loader.load(
        shipped_file=tmp_path / "missing-defaults.json",
        user_file=path,
        legacy_file=tmp_path / "missing-legacy.json",
        environ={},
    )

    assert loaded.value == expected
    assert not tuple(tmp_path.glob("*.tmp"))


def test_invalid_environment_override_is_rejected(tmp_path) -> None:
    with pytest.raises(ConfigurationError):
        ConfigurationLoader().load(
            shipped_file=tmp_path / "missing-defaults.json",
            user_file=tmp_path / "missing-user.json",
            legacy_file=tmp_path / "missing-legacy.json",
            environ={"LLUNA_HARDWARE_ACCELERATION": "sometimes"},
        )


def test_configuration_boundary_does_not_import_qt() -> None:
    code = (
        "import sys; import backend.configuration; "
        "assert not any(n.startswith(('PySide6', 'qfluentwidgets')) "
        "for n in sys.modules)"
    )
    subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        check=True,
        env=os.environ.copy(),
    )
